"""Explicit preservation of a legacy container before customer package upgrade."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import subprocess
import stat
from typing import Callable

from .account_bootstrap import NativeAccountTransport, SiteAccountProvisioner
from .credential_bootstrap import (
    BootstrapError, RootBootstrapAuthorization, SiteCredentialState, SiteCredentialStore,
)


class DockerReadOnlyAccountInspection:
    """Run the existing authenticated native adapter in a running legacy site."""

    PATHS = frozenset({
        "/objects/user_config/dwlabcmkadm", "/objects/user_config/dwlab-automation",
        "/objects/user_role/dwlab_automation",
        "/domain-types/activation_run/collections/pending_changes",
        "/domain-types/site_connection/collections/all",
    })

    def __init__(self, site: str, runner: Callable = subprocess.run) -> None:
        self._site, self._runner = site, runner
        self._native = NativeAccountTransport(runner=self._execute)

    def _execute(self, arguments: list[str], **kwargs) -> subprocess.CompletedProcess:
        return self._runner(["docker", "--host", "unix:///var/run/docker.sock", "exec", "-i",
                             self._site, *arguments], **kwargs)

    def request(self, state: SiteCredentialState, username: str, password: str,
                method: str, path: str, *, body: dict | None = None,
                etag: str | None = None) -> dict:
        """No HTTP listener, activation, writes or credentials in command arguments."""
        RootBootstrapAuthorization().require_root()
        if (state.site != self._site or method != "GET" or path not in self.PATHS
                or body is not None or etag is not None or username != "cmkadmin"):
            raise BootstrapError("Legacy inspection permits only site-bound authenticated reads.")
        return self._native.request(state, username, password, method, path)


class LegacyContainerMigration:
    """Capture only approved local Docker state; never publish inspect output."""

    def __init__(self, store: SiteCredentialStore, runner: Callable = subprocess.run) -> None:
        self._store, self._runner = store, runner

    def _run(self, arguments: list[str], *, output=subprocess.PIPE):
        try:
            result = self._runner(
                ["docker", "--host", "unix:///var/run/docker.sock", *arguments],
                stdout=output, stderr=subprocess.DEVNULL, timeout=180, check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
        except (OSError, subprocess.SubprocessError):
            raise BootstrapError("Legacy Docker migration command failed; output suppressed.") from None
        if result.returncode:
            raise BootstrapError("Legacy Docker migration failed; original container retained.")
        return result

    def check(self, site: str) -> None:
        """Refuse destructive container replacement without private recovery state."""
        RootBootstrapAuthorization().require_root()
        with self._store.transaction(site) as transaction:
            transaction.raise_if_failed()
            state = transaction.load()
            if state is None:
                raise BootstrapError("Run approved legacy-container migration before replacing this existing container.")
            if state.phase != "accounts-ready":
                backup = self._store.root / site / "before-migration.tar.gz"
                info = backup.lstat()
                if (not state.legacy_migration or not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.geteuid() or info.st_nlink != 1
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size == 0):
                    raise BootstrapError("Existing container migration is not safely prepared.")

    def prepare(self, site: str, *, approved: bool = False) -> None:
        """Stop OMD, privately back up accounts and preserve the original secret."""
        RootBootstrapAuthorization().require_root()
        if approved is not True:
            raise BootstrapError("Legacy-container migration requires explicit approval.")
        with self._store.transaction(site) as transaction:
            state = transaction.load()
            if state is not None:
                raise BootstrapError("Credential state already exists; review or resume the recorded migration.")
            result = self._run(["inspect", "--type", "container", site])
            try:
                data = json.loads(result.stdout)
                config = data[0]["Config"]
                environment = dict(entry.split("=", 1) for entry in config["Env"] if "=" in entry)
                old_password = environment["CMK_PASSWORD"]
                if environment.get("CMK_SITE_ID") != site:
                    raise ValueError
                if (not 1 <= len(old_password) <= 1024
                        or any(c in old_password for c in "\r\n\x00")):
                    raise ValueError
            except (TypeError, ValueError, KeyError, IndexError):
                raise BootstrapError("Cannot identify a supported legacy container credential.") from None
            for option in ("-u", "-g"):
                identity = self._run(["exec", site, "id", option, site])
                if identity.stdout.strip() != b"1000":
                    raise BootstrapError("Legacy container site UID/GID requires explicit migration review.")
            candidate = replace(SiteCredentialState.generate(site, 1000, 1000),
                                phase="awaiting-accounts", bootstrap_password=old_password,
                                legacy_migration=True)
            logger = logging.getLogger(__name__)
            logger.info("STEP START: operation=cmk-container-migration phase=read-only-legacy-preflight site=%s", site)
            SiteAccountProvisioner(DockerReadOnlyAccountInspection(site, self._runner)).assert_absent(candidate)
            logger.info("STEP PASS: operation=cmk-container-migration phase=read-only-legacy-preflight site=%s old_site_unchanged=true", site)
            self._run(["exec", site, "omd", "stop", site], output=subprocess.DEVNULL)
            backup = self._store.root / site / "before-migration.tar.gz"
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                self._run(["exec", site, "tar", "-C", f"/omd/sites/{site}",
                           "-czf", "-", "etc", "var/check_mk/web"], output=stream)
                stream.flush()
                os.fsync(stream.fileno())
                if stream.tell() == 0:
                    raise BootstrapError("Legacy container recovery archive is empty.")
            transaction.save(candidate)


class ContainerMigrationCli:
    """Root-only explicit upgrade preparation and pre-removal guard."""

    def run(self, argv: list[str] | None = None) -> int:
        from dwlabbasicpy.dwlabLogging import UtcLogFormatter

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=["prepare", "check"])
        parser.add_argument("--site", required=True)
        parser.add_argument("--credential-root", required=True, type=Path)
        parser.add_argument("--approve-existing-site", action="store_true")
        args = parser.parse_args(argv)
        logger = logging.Logger("dwlabcmkapi.container-migration")
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(UtcLogFormatter())
        logger.addHandler(handler)
        logger.info("STEP START: operation=cmk-container-migration action=%s site=%r", args.command, args.site)
        try:
            migration = LegacyContainerMigration(SiteCredentialStore(args.credential_root))
            if args.command == "prepare":
                migration.prepare(args.site, approved=args.approve_existing_site)
            else:
                migration.check(args.site)
        except BootstrapError as error:
            logger.error("STEP FAIL: operation=cmk-container-migration code=%s reason=%s; no automatic activation or discard", error.code.identifier, error.code.message)
            return 1
        except (OSError, ValueError) as error:
            logger.error("STEP FAIL: operation=cmk-container-migration failure=%s; review required before replacement", type(error).__name__)
            return 1
        logger.info("STEP PASS: operation=cmk-container-migration site=%s", args.site)
        return 0


if __name__ == "__main__":
    raise SystemExit(ContainerMigrationCli().run())
