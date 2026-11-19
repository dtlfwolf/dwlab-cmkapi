"""Root-only installation adapter for private, target-generated site accounts."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import secrets
import stat

import yaml
from dwlabbasicpy.dwlabLogging import UtcLogFormatter

from .account_bootstrap import AccountCompletionResult, NativeAccountTransport, SiteAccountCompletion
from .credential_bootstrap import (
    BootstrapAuthorization, BootstrapError, NewSiteCredentialPreparation, OmdBootstrapBackend,
    RootBootstrapAuthorization, SiteCredentialStore,
)
from .credential_migration import ExistingSiteCredentialMigration


class PrivateInstallationSettings:
    """Update only authentication settings after successful account verification."""

    def __init__(self, path: Path, authorization: BootstrapAuthorization | None = None) -> None:
        self.path = Path(path)
        self._authorization = authorization or RootBootstrapAuthorization()
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise BootstrapError("Installation settings require an absolute path.")

    def read(self) -> tuple[dict, bytes]:
        """Read a root-owned non-linked private file without following symlinks."""
        self._authorization.require_root()
        for parent in self.path.parents:
            info = parent.lstat()
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, os.geteuid()}
                    or (info.st_mode & 0o022 and not sticky_root)):
                raise BootstrapError("Untrusted installation settings ancestry.")
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                raise BootstrapError("Installation settings must be root-owned, singly linked and mode 0600.")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(1048577)
            if len(raw) > 1048576:
                raise BootstrapError("Installation settings exceed their size limit.")
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                raise BootstrapError("Installation settings must be a YAML mapping.")
            return data, raw
        finally:
            os.close(descriptor)

    def publish(self, data: dict, original: bytes, store: SiteCredentialStore, site: str) -> None:
        """Preserve an original recovery copy, then atomically replace only YAML."""
        self._authorization.require_root()
        with store.transaction(site) as transaction:
            state = transaction.load()
            if state is None or state.phase != "accounts-ready":
                raise BootstrapError("Cannot publish unverified credentials.")
            backup = store.root / site / "settings.before-bootstrap.yaml"
            try:
                descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                info = backup.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
                    raise BootstrapError("Unsafe existing settings backup.")
            else:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            updated = dict(data)
            updated.pop("cmkadmin_password", None)
            updated.pop("cmkadmin_username", None)
            updated["cmkCredentialsFile"] = str(store.root / site / "credentials.json")
            current, raw = self.read()
            if raw != original or current != data:
                raise BootstrapError("Installation settings changed concurrently; no overwrite performed.")
            temporary = self.path.with_name(f".credentials-settings-{secrets.token_hex(12)}")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(descriptor, "w") as stream:
                    yaml.safe_dump(updated, stream, sort_keys=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                parent = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            finally:
                temporary.unlink(missing_ok=True)


class SiteInstallation:
    """Coordinate shared provisioning without starting or exposing the site."""

    def __init__(self, store: SiteCredentialStore, logger: logging.Logger | None = None) -> None:
        self._store = store
        self._logger = logger or logging.getLogger(__name__)

    def configure(self, settings_file: Path, *, migrate: bool = False,
                  approved: bool = False) -> AccountCompletionResult:
        """Prepare new sites, or migrate existing sites only with explicit approval."""
        RootBootstrapAuthorization().require_root()
        settings = PrivateInstallationSettings(settings_file)
        data, raw = settings.read()
        site = data.get("cmkSite")
        with self._store.transaction(site) as transaction:
            existing = transaction.load()
        if migrate and not approved:
            raise BootstrapError("Existing-site migration requires explicit approval.")
        if existing is not None and existing.phase == "accounts-ready":
            result = SiteAccountCompletion(self._store, NativeAccountTransport(), logger=self._logger).complete(site)
        elif migrate:
            result = ExistingSiteCredentialMigration(self._store, logger=self._logger).migrate(
                site, data.get("cmkadmin_password"), approved=approved,
            )
        else:
            uid, gid = data.get("cmkSiteUID"), data.get("cmkSiteGID")
            NewSiteCredentialPreparation(self._store, OmdBootstrapBackend(), logger=self._logger).prepare(site, uid, gid)
            result = SiteAccountCompletion(self._store, NativeAccountTransport(), logger=self._logger).complete(site)
        settings.publish(data, raw, self._store, site)
        self._logger.info("STEP PASS: operation=cmk-site-installation phase=credential-reference-published site=%s activation_performed=false", site)
        return result


class SiteInstallationCli:
    """Accept configuration references, never command-line passwords."""

    def run(self, argv: list[str] | None = None) -> int:
        """Expose explicit fresh-install and existing-install operations."""
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=["provision-new-site", "migrate-existing-site"])
        parser.add_argument("--settings", required=True, type=Path)
        parser.add_argument("--credential-root", type=Path,
                            default=Path("/var/lib/dwlab/dwlabcmkapi/credentials"))
        parser.add_argument("--approve-existing-site", action="store_true")
        parser.add_argument("--run-id")
        args = parser.parse_args(argv)
        logger = logging.Logger("dwlabcmkapi.site-installation")
        handler = logging.StreamHandler()
        handler.setFormatter(UtcLogFormatter(run_id=args.run_id))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.info("STEP START: operation=cmk-site-installation action=%s", args.command)
        try:
            result = SiteInstallation(SiteCredentialStore(args.credential_root), logger).configure(
                args.settings, migrate=args.command == "migrate-existing-site",
                approved=args.approve_existing_site,
            )
        except (BootstrapError, OSError, ValueError, TypeError, yaml.YAMLError) as error:
            logger.error("STEP FAIL: operation=cmk-site-installation failure=%s; activation blocked", type(error).__name__)
            return 1
        print(json.dumps(vars(result)))
        return 0


if __name__ == "__main__":
    raise SystemExit(SiteInstallationCli().run())
