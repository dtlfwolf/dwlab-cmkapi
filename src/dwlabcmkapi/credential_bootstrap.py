"""Opt-in, stopped-site credential preparation; never activates a Checkmk site."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import Enum
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
from typing import Callable, Iterator, Protocol


class BootstrapFailureCode(Enum):
    """Reviewed, secret-free diagnostics suitable for files and operator logs."""

    PENDING_CHANGES = ("PENDING_CHANGES", "Unactivated Checkmk changes require operator review; no automatic activation is permitted.")
    ACCOUNT_CONFLICT = ("ACCOUNT_CONFLICT", "Reserved replacement accounts or role already exist and require review.")
    REPLICATION_ENABLED = ("REPLICATION_ENABLED", "Remote configuration/user replication must be reviewed before independent accounts are provisioned.")
    INVALID_STATE = ("INVALID_STATE", "Private credential or failure state is invalid or has unsafe permissions.")
    NATIVE_OPERATION = ("NATIVE_OPERATION", "Authenticated native Checkmk inspection failed; review the existing site and credentials.")
    GENERIC = ("BOOTSTRAP_FAILED", "Checkmk bootstrap failed; inspect the private recovery state before retrying.")

    @property
    def identifier(self) -> str:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class BootstrapError(RuntimeError):
    """Credential preparation failed without exposing sensitive diagnostics."""

    def __init__(self, message: str, *, code: BootstrapFailureCode = BootstrapFailureCode.GENERIC) -> None:
        if not isinstance(code, BootstrapFailureCode):
            raise TypeError("Invalid bootstrap failure code")
        self.code = code
        super().__init__(message)


class BootstrapAuthorization(Protocol):
    """Authorize local provisioning using a verified OS identity."""

    def require_root(self) -> None:
        """Reject identities not permitted to provision sites."""
        ...


class RootBootstrapAuthorization:
    """Default local management boundary; no environment identity claims."""

    def require_root(self) -> None:
        """Require the effective OS root identity."""
        if os.geteuid() != 0:
            raise BootstrapError("New-site preparation requires OS root privileges.")


@dataclass(frozen=True, repr=False)
class SiteCredentialState:
    """Private material; intentionally excluded from repr and console output."""

    site: str
    uid: int
    gid: int
    phase: str
    bootstrap_password: str
    emergency_password: str
    automation_secret: str
    legacy_migration: bool = False
    bootstrap_changes: tuple[str, ...] = ()
    activation_id: str = ""
    activation_complete: bool = False

    @classmethod
    def generate(cls, site: str, uid: int, gid: int) -> SiteCredentialState:
        """Generate independent 256-bit secrets on the installation target."""
        return cls(site, uid, gid, "prepared", *(secrets.token_hex(32) for _ in range(3)))


class CredentialTransaction:
    """Read and atomically update private state under an exclusive site lock."""

    def __init__(self, descriptor: int, site: str) -> None:
        self._directory = descriptor
        self._site = site

    def _check_file(self, descriptor: int) -> None:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise BootstrapError("Credential files must be private, singly linked and OS-owned.", code=BootstrapFailureCode.INVALID_STATE)

    def load(self) -> SiteCredentialState | None:
        """Load validated state without following links or repairing permissions."""
        try:
            descriptor = os.open(
                "credentials.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=self._directory,
            )
        except FileNotFoundError:
            return None
        try:
            self._check_file(descriptor)
            raw = os.read(descriptor, 16385)
            if len(raw) > 16384:
                raise BootstrapError("Credential state exceeds its size limit.")
            try:
                data = json.loads(raw)
                if not isinstance(data, dict) or data.pop("schema_version", None) != 1:
                    raise ValueError
                if data.get("phase") == "accounts-ready":
                    data.setdefault("bootstrap_password", "")
                if "bootstrap_changes" in data:
                    if not isinstance(data["bootstrap_changes"], list):
                        raise ValueError
                    data["bootstrap_changes"] = tuple(data["bootstrap_changes"])
                state = SiteCredentialState(**data)
                self._validate(state)
                return state
            except (TypeError, ValueError, KeyError):
                raise BootstrapError("Invalid credential state; manual review required.") from None
        finally:
            os.close(descriptor)

    def _validate(self, state: SiteCredentialState) -> None:
        values = (state.emergency_password, state.automation_secret)
        phases = {"prepared", "creating", "created", "awaiting-accounts",
                  "provisioning-accounts", "retiring-bootstrap", "accounts-ready"}
        if state.phase != "accounts-ready" and not state.legacy_migration:
            values += (state.bootstrap_password,)
        if (state.site != self._site
                or type(state.uid) is not int or state.uid < 1
                or type(state.gid) is not int or state.gid < 1
                or state.phase not in phases
                or type(state.legacy_migration) is not bool
                or type(state.activation_complete) is not bool
                or (state.activation_complete and state.phase != "accounts-ready")
                or not isinstance(state.activation_id, str)
                or (state.activation_id and (state.phase != "accounts-ready"
                    or not re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", state.activation_id)))
                or not isinstance(state.bootstrap_changes, tuple)
                or len(state.bootstrap_changes) > 3
                or len(set(state.bootstrap_changes)) != len(state.bootstrap_changes)
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in state.bootstrap_changes)
                or (state.legacy_migration and state.phase != "accounts-ready"
                    and (not isinstance(state.bootstrap_password, str)
                         or not 1 <= len(state.bootstrap_password) <= 1024
                         or any(c in state.bootstrap_password for c in "\r\n\x00")))
                or (state.phase == "accounts-ready" and state.bootstrap_password != "")
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                       for value in values)
                or len(set(values)) != len(values)):
            raise BootstrapError("Invalid credential state; manual review required.")

    def save(self, state: SiteCredentialState) -> None:
        """Persist a complete record atomically, preserving secrets on retries."""
        self._validate(state)
        data = {"schema_version": 1, **vars(state)}
        if state.phase == "accounts-ready":
            del data["bootstrap_password"]
        self._publish("credentials.json", data)

    def load_failure(self) -> BootstrapFailureCode | None:
        """Read only validated, site-bound, root-private failure codes."""
        try:
            descriptor = os.open(".bootstrap-failure.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=self._directory)
        except FileNotFoundError:
            return None
        try:
            self._check_file(descriptor)
            raw = os.read(descriptor, 2049)
            if len(raw) > 2048:
                raise ValueError
            data = json.loads(raw)
            if (not isinstance(data, dict) or set(data) != {"schema_version", "site", "code"}
                    or data["schema_version"] != 1 or data["site"] != self._site):
                raise ValueError
            for code in BootstrapFailureCode:
                if code.identifier == data["code"]:
                    return code
            raise ValueError
        except (ValueError, TypeError, KeyError):
            raise BootstrapError("Invalid private bootstrap failure status.", code=BootstrapFailureCode.INVALID_STATE) from None
        finally:
            os.close(descriptor)

    def raise_if_failed(self) -> None:
        """Fail immediately rather than waiting for an intentionally blocked API."""
        code = self.load_failure()
        if code is not None:
            raise BootstrapError(f"Bootstrap blocked [{code.identifier}]: {code.message}", code=code)

    def record_failure(self, code: BootstrapFailureCode) -> None:
        """Persist an allowlisted code, never exception text or customer data."""
        if not isinstance(code, BootstrapFailureCode):
            raise TypeError("Invalid bootstrap failure code")
        self.load_failure()
        self._publish(".bootstrap-failure.json", {"schema_version": 1, "site": self._site,
                                                 "code": code.identifier})

    def clear_failure(self) -> None:
        """A new explicit container start revalidates instead of trusting old failure state."""
        if self.load_failure() is not None:
            os.unlink(".bootstrap-failure.json", dir_fd=self._directory)
            os.fsync(self._directory)

    def _publish(self, name: str, data: dict) -> None:
        temporary = f".credentials-{secrets.token_hex(16)}"
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=self._directory,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(data, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, name, src_dir_fd=self._directory,
                       dst_dir_fd=self._directory)
            os.fsync(self._directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=self._directory)
            except FileNotFoundError:
                pass


class SiteCredentialStore:
    """Independently deployable private store with symlink-safe directory walking."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute() or ".." in self.root.parts:
            raise BootstrapError("Credential root must be an absolute path without '..'.")

    @contextmanager
    def _directory(self, path: Path) -> Iterator[int]:
        descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in path.parts[1:]:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
                info = os.fstat(descriptor)
                sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
                if (info.st_uid not in {0, os.geteuid()}
                        or (info.st_mode & 0o022 and not sticky_root)):
                    raise BootstrapError("Untrusted credential directory ancestry.")
            info = os.fstat(descriptor)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise BootstrapError("Credential directories must be OS-owned with mode 0700.")
            yield descriptor
        finally:
            os.close(descriptor)

    @contextmanager
    def transaction(self, site: str) -> Iterator[CredentialTransaction]:
        """Serialize preparation; never replace unsafe existing paths or modes."""
        if not isinstance(site, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", site):
            raise BootstrapError("Invalid OMD site name.")
        with self._directory(self.root):
            with self._directory(self.root / site) as directory:
                lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW |
                               os.O_NONBLOCK, 0o600, dir_fd=directory)
                try:
                    transaction = CredentialTransaction(directory, site)
                    transaction._check_file(lock)
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    yield transaction
                finally:
                    os.close(lock)


class SiteBootstrapBackend(Protocol):
    """Local native operations; implementations must never start web services."""

    def verify_support(self) -> None: ...
    def exists(self, site: str) -> bool: ...
    def create(self, site: str, uid: int, gid: int) -> None: ...
    def is_stopped(self, site: str) -> bool: ...
    def set_bootstrap_password(self, site: str, password: str) -> None: ...


class OmdBootstrapBackend:
    """Checkmk 2.4/2.5 adapter using native cmk-passwd --stdin."""

    def __init__(self, sites_root: Path = Path("/omd/sites"),
                 runner: Callable = subprocess.run,
                 authorization: BootstrapAuthorization | None = None,
                 no_tmpfs: bool = False) -> None:
        self._sites_root = Path(sites_root)
        self._runner = runner
        self._authorization = authorization or RootBootstrapAuthorization()
        self._no_tmpfs = no_tmpfs

    def _run(self, arguments: list[str], *, input_bytes: bytes | None = None,
             capture: bool = False) -> subprocess.CompletedProcess:
        self._authorization.require_root()
        try:
            return self._runner(
                arguments, input=input_bytes, check=False, timeout=120,
                stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.SubprocessError):
            raise BootstrapError("Native bootstrap command could not complete; output suppressed.") from None

    def verify_support(self) -> None:
        """Fail closed for unverified Checkmk release lines."""
        result = self._run(["/usr/bin/omd", "version"], capture=True)
        if result.returncode or not re.search(rb"Version 2\.[45]\.", result.stdout):
            raise BootstrapError("Stopped-site bootstrap currently supports Checkmk 2.4 and 2.5 only.")

    def exists(self, site: str) -> bool:
        """Detect existing sites, including dangling symlinks; never adopt them."""
        self._authorization.require_root()
        return os.path.lexists(self._sites_root / site)

    def create(self, site: str, uid: int, gid: int) -> None:
        """Create a stopped site and discard OMD's initial-password output."""
        arguments = [
            "/usr/bin/omd", "create", "--no-autostart",
        ]
        if self._no_tmpfs:
            arguments.append("--no-tmpfs")
        result = self._run(arguments + ["-u", str(uid), "-g", str(gid), site])
        if result.returncode:
            raise BootstrapError(f"OMD site creation failed (exit {result.returncode}); sensitive output suppressed.")

    def is_stopped(self, site: str) -> bool:
        """OMD documents return code 1 for a completely stopped site."""
        return self._run(["/usr/bin/omd", "status", site]).returncode == 1

    def set_bootstrap_password(self, site: str, password: str) -> None:
        """Provide the password only through stdin in the site's login environment."""
        result = self._run(
            ["/usr/sbin/runuser", "--login", site, "--command", "cmk-passwd --stdin cmkadmin"],
            input_bytes=(password + "\n").encode("ascii"),
        )
        if result.returncode:
            raise BootstrapError(f"Bootstrap password setup failed (exit {result.returncode}); output suppressed.")


@dataclass(frozen=True)
class BootstrapPreparationResult:
    """Non-secret summary; this is not permission to expose or start the site."""

    site: str
    phase: str
    credential_file: str
    activation_allowed: bool = False


class NewSiteCredentialPreparation:
    """Prepare credentials idempotently without changing existing installations."""

    def __init__(self, store: SiteCredentialStore, backend: SiteBootstrapBackend,
                 authorization: BootstrapAuthorization | None = None,
                 logger: logging.Logger | None = None) -> None:
        self._store, self._backend = store, backend
        self._authorization = authorization or RootBootstrapAuthorization()
        self._logger = logger or logging.getLogger(__name__)

    def prepare(self, site: str, uid: int, gid: int) -> BootstrapPreparationResult:
        """Stop at awaiting-accounts; never activate, adopt or silently rotate."""
        caller_uid = os.geteuid()
        self._logger.info(
            "STEP START: operation=cmk-credential-prepare caller_uid=%s site=%r",
            caller_uid, site,
        )
        try:
            self._authorization.require_root()
            result = self._prepare_authorized(site, uid, gid)
        except (BootstrapError, OSError) as error:
            self._logger.error(
                "STEP FAIL: operation=cmk-credential-prepare caller_uid=%s site=%r failure=%s",
                caller_uid, site, type(error).__name__,
            )
            raise
        self._logger.info(
            "STEP PASS: operation=cmk-credential-prepare caller_uid=%s site=%r activation_allowed=false",
            caller_uid, site,
        )
        return result

    def _prepare_authorized(self, site: str, uid: int, gid: int) -> BootstrapPreparationResult:
        if type(uid) is not int or type(gid) is not int or min(uid, gid) < 1:
            raise BootstrapError("Site UID and GID must be positive integers.")
        self._backend.verify_support()
        with self._store.transaction(site) as transaction:
            state = transaction.load()
            exists = self._backend.exists(site)
            if state is None:
                if exists:
                    raise BootstrapError("Existing site is not owned by this preparation; migration requires review.")
                state = SiteCredentialState.generate(site, uid, gid)
                transaction.save(state)
                self._logger.info("STEP PASS: operation=cmk-credential-prepare phase=generate-private-state site=%s", site)
            if (state.uid, state.gid) != (uid, gid):
                raise BootstrapError("Requested UID/GID differ from the recorded preparation.")
            if state.phase in {"provisioning-accounts", "retiring-bootstrap", "accounts-ready"}:
                raise BootstrapError("Preparation has advanced; use complete-accounts for verification or recovery.")
            if state.phase == "creating":
                raise BootstrapError("Interrupted site creation requires manual review; no automatic adoption.")
            if state.phase == "prepared":
                if exists:
                    raise BootstrapError("Unexpected existing site; no automatic adoption.")
                transaction.save(replace(state, phase="creating"))
                self._backend.create(site, uid, gid)
                if not self._backend.exists(site):
                    raise BootstrapError("OMD reported success but the new site is missing; manual review required.")
                state = replace(state, phase="created")
                transaction.save(state)
            elif not exists:
                raise BootstrapError("Recorded site is missing; no automatic recreation or credential reset.")
            if not self._backend.is_stopped(site):
                raise BootstrapError("Site must remain completely stopped during credential preparation.")
            if state.phase == "created":
                self._backend.set_bootstrap_password(site, state.bootstrap_password)
                state = replace(state, phase="awaiting-accounts")
                transaction.save(state)
            self._logger.info("STEP PASS: operation=cmk-credential-prepare phase=awaiting-accounts site=%s activation_allowed=false", site)
            return BootstrapPreparationResult(
                site, state.phase, str(self._store.root / site / "credentials.json")
            )


class BootstrapCli:
    """Explicit opt-in entry point for new-site preparation only."""

    def run(self, argv: list[str] | None = None) -> int:
        """Print metadata only; never print credentials or native command output."""
        from dwlabbasicpy.dwlabLogging import UtcLogFormatter

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=["prepare-new-site"])
        parser.add_argument("--site", required=True)
        parser.add_argument("--site-uid", type=int, required=True)
        parser.add_argument("--site-gid", type=int, required=True)
        parser.add_argument("--run-id", help="Optional deployment correlation ID (not an identity)")
        parser.add_argument("--credential-root", type=Path,
                            default=Path("/var/lib/dwlab/dwlabcmkapi/credentials"))
        args = parser.parse_args(argv)
        logger = logging.Logger("dwlabcmkapi.bootstrap")
        handler = logging.StreamHandler()
        handler.setFormatter(UtcLogFormatter(run_id=args.run_id))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info("STEP START: operation=cmk-credential-prepare")
            result = NewSiteCredentialPreparation(
                SiteCredentialStore(args.credential_root), OmdBootstrapBackend(), logger=logger
            ).prepare(args.site, args.site_uid, args.site_gid)
        except BootstrapError as exc:
            logger.error("STEP FAIL: operation=cmk-credential-prepare reason=%s; no activation performed", exc)
            return 1
        except OSError as exc:
            logger.error("STEP FAIL: operation=cmk-credential-prepare filesystem=%s; no activation performed", exc.strerror)
            return 1
        print(json.dumps(vars(result)))
        return 0


if __name__ == "__main__":
    raise SystemExit(BootstrapCli().run())
