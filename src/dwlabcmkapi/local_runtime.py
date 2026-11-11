"""Linux Checkmk adapter. All lookups and probes run as the OMD site user."""

from __future__ import annotations

import fcntl
import ipaddress
import json
import re
import shlex
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .reconciliation import ReconciliationError
from .services import SiteConnectionState


class LocalCheckmkRuntime:
    """Execute bounded site operations, without shell interpolation.

    The caller needs root privileges for runuser. The lock coordinates DW-Lab
    workers; Checkmk's own activation locking still protects interactive work.
    A core regeneration activates site-wide configuration, including pending
    administrator changes, and must therefore be explicitly enabled by callers.
    """

    def __init__(self, site_name: str, state_root: Path,
                 allow_activation: bool = False, timeout: float = 120,
                 runner: Callable = subprocess.run,
                 monotonic: Callable = time.monotonic,
                 sleep: Callable = time.sleep) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", site_name):
            raise ValueError("Invalid OMD site name")
        self.site_name = site_name
        self._state_root = Path(state_root)
        self._allow_activation = allow_activation
        self._timeout = timeout
        self._runner = runner
        self._clock, self._sleep = monotonic, sleep

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Serialize all DW-Lab reconciliation workers for this OMD site."""
        self._state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self._state_root / f"{self.site_name}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _run(self, command):
        result = self._runner(
            ["runuser", "--login", self.site_name, "--command", shlex.join(command)],
            text=True, capture_output=True, timeout=self._timeout, check=False)
        if result.returncode:
            raise ReconciliationError(
                f"Site command failed: {command[0:2]} "
                f"exit={result.returncode} stderr={result.stderr.strip()} "
                f"stdout={result.stdout.strip()}")
        return result.stdout

    def _python(self, script, *arguments):
        return self._run(["python3", "-c", script, *map(str, arguments)])

    def resolve(self, hostname: str) -> set[str]:
        """Return usable IPv4 addresses visible to the site user."""
        raw = self._python(
            "import json,socket,sys\n"
            "try: a=sorted({r[4][0] for r in socket.getaddrinfo(sys.argv[1],None,socket.AF_INET)})\n"
            "except socket.gaierror: a=[]\n"
            "print(json.dumps(a))", hostname)
        return {str(ipaddress.IPv4Address(a)) for a in json.loads(raw)
                if not ipaddress.IPv4Address(a).is_unspecified
                and not ipaddress.IPv4Address(a).is_multicast
                and not ipaddress.IPv4Address(a).is_loopback}

    def refresh_dns(self, hostname: str, address: str) -> None:
        """Refresh Checkmk's persistent cache and verify its selected IPv4."""
        self._run(["cmk", "--update-dns-cache"])
        raw = self._python(
            "import ast,json,pathlib,sys; "
            "d=ast.literal_eval((pathlib.Path.home()/'var/check_mk/ipaddresses.cache').read_text()); "
            "print(json.dumps(d.get((sys.argv[1],4))))", hostname)
        actual = json.loads(raw)
        if actual != address:
            raise ReconciliationError(
                f"Checkmk DNS cache mismatch: host={hostname} expected={address} actual={actual}")

    def _live(self, query):
        return self._python(
            "import socket,sys,pathlib\n"
            "with socket.socket(socket.AF_UNIX) as s:\n"
            " s.settimeout(10); s.connect(str(pathlib.Path.home()/'tmp/run/live')); "
            "s.sendall(sys.argv[1].encode()); s.shutdown(socket.SHUT_WR)\n"
            " data=b''\n"
            " while True:\n"
            "  chunk=s.recv(65536)\n"
            "  if not chunk: break\n"
            "  data+=chunk\n"
            "  if len(data)>1048576: raise RuntimeError('Livestatus response too large')\n"
            " print(data.decode())", query)

    def _host(self, hostname):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", hostname):
            raise ValueError("Invalid monitoring hostname")
        return json.loads(self._live(
            "GET hosts\nColumns: address state has_been_checked last_check plugin_output\n"
            f"Filter: name = {hostname}\nOutputFormat: json\n\n"))

    def core_address(self, hostname: str) -> str:
        """Read the effective address from running-core Livestatus."""
        rows = self._host(hostname)
        return rows[0][0] if rows else ""

    def reload(self) -> None:
        """Regenerate configuration using the installed monitoring-core type."""
        if not self._allow_activation:
            raise ReconciliationError("Site-wide activation is not enabled")
        core = self._run(["omd", "config", "show", "CORE"]).strip()
        if core not in {"nagios", "cmc"}:
            raise ReconciliationError(f"Unsupported monitoring core: {core!r}")
        self._run(["cmk", "-R" if core == "nagios" else "-O"])

    def verify(self, hostname: str, address: str,
               connection: SiteConnectionState) -> None:
        """Verify a fresh host check and the configured remote Livestatus transport."""
        if connection.connection_host != hostname or connection.connection_socket_type != "tcp":
            raise ReconciliationError("Remote site connection does not target the managed host over TCP")
        # Ask for a real check, never inject an UP result into the core.
        requested = int(time.time())
        self._live(f"COMMAND [{requested}] SCHEDULE_FORCED_HOST_CHECK;{hostname};{requested}\n\n")
        deadline = self._clock() + self._timeout
        rows = []
        while True:
            rows = self._host(hostname)
            if (rows and rows[0][0] == address and rows[0][1] == 0
                    and rows[0][2] and rows[0][3] >= requested):
                break
            if self._clock() >= deadline:
                raise ReconciliationError(
                    f"Core verification failed: host={hostname} expected={address} actual={rows}")
            self._sleep(1)
        self.probe_livestatus(hostname, address, connection)

    def probe_livestatus(self, hostname: str, address: str,
                         connection: SiteConnectionState) -> None:
        """Read remote status using the configured port and TLS verification policy."""
        self._python(
            "import json,socket,ssl,sys\n"
            "host,ip,port,encrypted,verify=sys.argv[1:]\n"
            "s=socket.create_connection((ip,int(port)),timeout=10)\n"
            "try:\n"
            " if encrypted=='True':\n"
            "  ctx=ssl.create_default_context()\n"
            "  if verify!='True': ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE\n"
            "  s=ctx.wrap_socket(s,server_hostname=host)\n"
            " s.sendall(b'GET status\\nColumns: program_version\\nOutputFormat: json\\n\\n')\n"
            " s.shutdown(socket.SHUT_WR) if encrypted!='True' else None\n"
            " data=b''\n"
            " while b'\\n' not in data:\n"
            "  chunk=s.recv(4096)\n"
            "  if not chunk: break\n"
            "  data+=chunk\n"
            "  if len(data)>65536: raise RuntimeError('Remote Livestatus response too large')\n"
            " if not json.loads(data): raise RuntimeError('Empty remote Livestatus status')\n"
            "finally: s.close()", hostname, address, connection.connection_port,
            connection.connection_encrypted, connection.connection_verify)
