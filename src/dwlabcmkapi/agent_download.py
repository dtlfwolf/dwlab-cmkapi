"""Download local client agents without password arguments, env or netrc files."""

from __future__ import annotations

import argparse
from email.message import Message
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable

import requests

from .credential_bootstrap import BootstrapError, RootBootstrapAuthorization
from .credential_provider import SiteAutomationCredentialProvider


class LocalAgentDownloader:
    """A fixed loopback destination with in-memory, per-site automation auth."""

    FORMATS = {"linux_deb": ".deb", "linux_rpm": ".rpm", "windows_msi": ".msi"}

    def __init__(self, provider: SiteAutomationCredentialProvider | None = None,
                 session_factory: Callable[[], requests.Session] = requests.Session,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 logger: logging.Logger | None = None) -> None:
        self._provider = provider or SiteAutomationCredentialProvider()
        self._session_factory = session_factory
        self._clock, self._sleep = clock, sleep
        self._logger = logger or logging.getLogger(__name__)

    def download(self, site: str, credential_file: Path, port: int,
                 destination: Path, *, timeout: float = 1200) -> None:
        """Wait for the bootstrap gate and API; publish only complete downloads."""
        RootBootstrapAuthorization().require_root()
        if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", site)
                or type(port) is not int or not 1 <= port <= 65535 or timeout <= 0):
            raise BootstrapError("Invalid local agent-download target.")
        deadline = self._clock() + timeout
        credential = None
        self._logger.info("STEP START: operation=cmk-agent-download phase=wait-credential-gate site=%s", site)
        while credential is None:
            credential = self._provider.find_ready(credential_file, site)
            if credential is None:
                self._wait(deadline)
        root = f"http://127.0.0.1:{port}/{site}/check_mk/api/1.0"
        destination = Path(destination)
        if not destination.is_absolute() or ".." in destination.parts:
            raise BootstrapError("Agent destination must be an absolute directory.")
        destination.mkdir(parents=True, exist_ok=True)
        with self._session_factory() as session:
            session.trust_env = False
            session.headers.update({"Authorization": f"Bearer {credential.username} {credential.secret}"})
            while True:
                self._wait_for_api(session, root, site, deadline)
                try:
                    with tempfile.TemporaryDirectory(prefix=".agents-", dir=destination) as temporary:
                        files = []
                        for os_type, suffix in self.FORMATS.items():
                            path = self._download_one(session, root, os_type, suffix, Path(temporary), deadline)
                            files.append(path)
                        for path in files:
                            os.replace(path, destination / path.name)
                        self._logger.info("STEP PASS: operation=cmk-agent-download phase=publish site=%s files=%s", site, len(files))
                    return
                except requests.exceptions.SSLError:
                    raise
                except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as error:
                    self._logger.info("STEP RETRY: operation=cmk-agent-download phase=transient-runtime-restart site=%s failure=%s", site, type(error).__name__)
                    self._wait(deadline)

    def _wait_for_api(self, session: requests.Session, root: str, site: str, deadline: float) -> None:
        while True:
            if self._clock() >= deadline:
                raise BootstrapError("Timed out waiting for local Checkmk API readiness.")
            try:
                response = session.get(root + "/version", timeout=10, allow_redirects=False)
            except requests.exceptions.SSLError:
                raise
            except (requests.ConnectionError, requests.Timeout):
                self._wait(deadline)
                continue
            with response:
                if response.status_code in {401, 403}:
                    raise BootstrapError("Local agent API rejected automation authentication.")
                if 300 <= response.status_code < 400:
                    raise BootstrapError("Local agent API redirects are not allowed.")
                if response.status_code == 200:
                    identity = response.json()
                    if isinstance(identity, dict) and identity.get("site") == site:
                        self._logger.info("STEP PASS: operation=cmk-agent-download phase=authenticated-api-ready site=%s", site)
                        return
            self._wait(deadline)

    def _wait(self, deadline: float) -> None:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise BootstrapError("Timed out waiting for local Checkmk credentials/API readiness.")
        self._sleep(min(5, remaining))

    def _download_one(self, session, root: str, os_type: str,
                      suffix: str, destination: Path, deadline: float) -> Path:
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise BootstrapError("Timed out downloading local Checkmk agents.")
        with session.get(root + "/domain-types/agent/actions/download/invoke",
                         params={"os_type": os_type}, timeout=min(120, remaining),
                         allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise BootstrapError(f"Agent download failed for {os_type} (HTTP {response.status_code}).")
            header = Message()
            disposition = response.headers.get("Content-Disposition", "")
            if any(character in disposition for character in "\r\n\x00"):
                raise BootstrapError("Unsafe agent download filename.")
            header["Content-Disposition"] = disposition
            name = header.get_filename() or "check-mk-agent" + suffix
            if not re.fullmatch(r"[A-Za-z0-9_+.-]+" + re.escape(suffix), name):
                raise BootstrapError("Unsafe agent download filename.")
            path = destination / name
            total = 0
            with path.open("xb") as stream:
                for block in response.iter_content(65536):
                    if self._clock() >= deadline:
                        raise BootstrapError("Timed out streaming a local Checkmk agent.")
                    total += len(block)
                    if total > 200 * 1024 * 1024:
                        raise BootstrapError("Agent download exceeds its size limit.")
                    stream.write(block)
            if total == 0:
                raise BootstrapError("Agent download is empty.")
            return path


class AgentDownloadCli:
    """Root-only shell adapter; inputs identify state, not secret values."""

    def run(self, argv: list[str] | None = None) -> int:
        from dwlabbasicpy.dwlabLogging import UtcLogFormatter

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--site", required=True)
        parser.add_argument("--credential-file", required=True, type=Path)
        parser.add_argument("--port", required=True, type=int)
        parser.add_argument("--destination", required=True, type=Path)
        args = parser.parse_args(argv)
        logger = logging.Logger("dwlabcmkapi.agent-download")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(UtcLogFormatter())
        logger.addHandler(handler)
        try:
            LocalAgentDownloader(logger=logger).download(args.site, args.credential_file, args.port, args.destination)
        except BootstrapError as error:
            logger.error("STEP FAIL: operation=cmk-agent-download reason=%s", error)
            return 1
        except (OSError, ValueError, requests.RequestException) as error:
            logger.error("STEP FAIL: operation=cmk-agent-download failure=%s", type(error).__name__)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(AgentDownloadCli().run())
