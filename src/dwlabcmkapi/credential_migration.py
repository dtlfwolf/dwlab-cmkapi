"""Explicit stopped-site migration with a private recovery backup."""

from __future__ import annotations

from dataclasses import replace
import logging
import os
from pathlib import Path
import pwd
import tarfile
from typing import Callable

from .account_bootstrap import AccountCompletionResult, AccountTransport, NativeAccountTransport, SiteAccountCompletion
from .credential_bootstrap import (
    BootstrapAuthorization, BootstrapError, OmdBootstrapBackend,
    RootBootstrapAuthorization, SiteBootstrapBackend, SiteCredentialState, SiteCredentialStore,
)


class SiteMigrationBackup:
    """Preserve account/role configuration privately; never overwrite a backup."""

    def __init__(self, sites_root: Path = Path("/omd/sites")) -> None:
        self._sites_root = sites_root

    def create(self, site: str, destination: Path) -> None:
        """Keep symlinks as links, not dereferenced external content."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(destination, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                with tarfile.open(fileobj=stream, mode="w:gz", dereference=False) as archive:
                    for relative in ("etc", "var/check_mk/web"):
                        source = self._sites_root / site / relative
                        if not source.is_dir() or source.is_symlink():
                            raise BootstrapError("Migration backup source is missing or is a symlink.")
                        archive.add(source, arcname=relative)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            # An incomplete backup is retained for review, never silently reused.
            raise BootstrapError("Private migration backup failed; no accounts changed.") from None


class ExistingSiteCredentialMigration:
    """Never reset the old password to adopt an existing site."""

    def __init__(self, store: SiteCredentialStore, backend: SiteBootstrapBackend | None = None,
                 transport: AccountTransport | None = None,
                 backup: SiteMigrationBackup | None = None,
                 authorization: BootstrapAuthorization | None = None,
                 identity_lookup: Callable[[str], pwd.struct_passwd] = pwd.getpwnam,
                 logger: logging.Logger | None = None) -> None:
        self._authorization = authorization or RootBootstrapAuthorization()
        self._store = store
        self._backend = backend or OmdBootstrapBackend(authorization=self._authorization)
        self._transport = transport or NativeAccountTransport(authorization=self._authorization)
        self._backup = backup or SiteMigrationBackup()
        self._identity_lookup = identity_lookup
        self._logger = logger or logging.getLogger(__name__)

    def migrate(self, site: str, old_password: str, *, approved: bool = False) -> AccountCompletionResult:
        """Back up and verify replacement accounts before retiring old access."""
        self._authorization.require_root()
        if approved is not True:
            raise BootstrapError("Existing-site migration requires explicit approval.")
        if (not isinstance(old_password, str) or not 1 <= len(old_password) <= 1024
                or any(c in old_password for c in "\r\n\x00")):
            raise BootstrapError("Invalid legacy bootstrap credential.")
        self._logger.info("STEP START: operation=cmk-existing-site-migration site=%r caller_uid=%s", site, os.geteuid())
        self._backend.verify_support()
        with self._store.transaction(site) as transaction:
            if not self._backend.exists(site) or not self._backend.is_stopped(site):
                raise BootstrapError("Existing-site migration requires a completely stopped site.")
            state = transaction.load()
            account = self._identity_lookup(site)
            if state is None:
                state = replace(
                    SiteCredentialState.generate(site, account.pw_uid, account.pw_gid),
                    phase="awaiting-accounts", bootstrap_password=old_password,
                    legacy_migration=True,
                )
                # Prove the old credential and reject collisions before backup or mutation.
                self._transport.verify_site(state)
                from .account_bootstrap import SiteAccountProvisioner
                SiteAccountProvisioner(self._transport).assert_absent(state)
                self._backup.create(site, self._store.root / site / "before-migration.tar.gz")
                transaction.save(state)
                self._logger.info("STEP PASS: operation=cmk-existing-site-migration phase=private-backup site=%s", site)
            elif (not state.legacy_migration
                  or (state.uid, state.gid) != (account.pw_uid, account.pw_gid)):
                raise BootstrapError("Existing private state does not belong to this migration.")
        result = SiteAccountCompletion(
            self._store, self._transport, self._authorization, self._logger,
        ).complete(site)
        self._logger.info("STEP PASS: operation=cmk-existing-site-migration site=%s activation_performed=false", site)
        return result
