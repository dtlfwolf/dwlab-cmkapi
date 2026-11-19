"""Portable, target-local Checkmk bootstrap before container network startup."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import time

from .credential_bootstrap import (
    BootstrapError, NewSiteCredentialPreparation, OmdBootstrapBackend,
    RootBootstrapAuthorization, SiteCredentialStore,
)
from .account_bootstrap import NativeAccountTransport, SiteAccountCompletion
from .account_activation import BootstrapChangeActivation
from .container_runtime import ContainerRuntimePreparation


class ContainerSiteBootstrap:
    """Own the credential gate; Docker entrypoints only invoke this service."""

    def __init__(self, store: SiteCredentialStore, backend: OmdBootstrapBackend | None = None,
                 transport: NativeAccountTransport | None = None,
                 sites_root: Path = Path("/omd/sites")) -> None:
        self._store = store
        self._backend = backend or OmdBootstrapBackend(no_tmpfs=True)
        self._transport = transport or NativeAccountTransport()
        self._sites_root = sites_root

    def configure(self, site: str) -> None:
        """Create stopped sites, verify accounts on every start, then enable autostart."""
        RootBootstrapAuthorization().require_root()
        with self._store.transaction(site) as transaction:
            state = transaction.load()
        exists = self._backend.exists(site)
        if exists:
            if state is None:
                raise BootstrapError("Existing container site requires explicit credential migration before replacement.")
            configuration = self._sites_root / site / "etc"
            if (not configuration.is_dir() or configuration.is_symlink()
                    or not (configuration / "omd/site.conf").is_file()):
                raise BootstrapError("Existing container site configuration is damaged; automatic recreation is refused.")
            # Vendor entrypoint reconstructs OS accounts/version links for a mounted
            # volume, then exits for this non-default command without starting OMD.
            result = self._backend._run([
                "/usr/bin/env", f"CMK_SITE_ID={site}", "/docker-entrypoint.sh", "/bin/true",
            ])
            if result.returncode:
                raise BootstrapError("Cannot prepare the existing container site identity.")
        if state is None or state.phase in {"prepared", "creating", "created", "awaiting-accounts"}:
            NewSiteCredentialPreparation(self._store, self._backend).prepare(site, 1000, 1000)
        with self._store.transaction(site) as transaction:
            state = transaction.load()
        ContainerRuntimePreparation(self._backend, self._sites_root).prepare(state)
        SiteAccountCompletion(self._store, self._transport).complete(site)
        for option, value in (
            ("APACHE_TCP_ADDR", "0.0.0.0"), ("APACHE_TCP_PORT", "5000"),
            ("LIVESTATUS_TCP", "on"), ("AUTOSTART", "on"),
        ):
            if self._backend._run(["/usr/bin/omd", "config", site, "set", option, value]).returncode:
                raise BootstrapError("Container service configuration failed; startup blocked.")
        apache = self._sites_root / site / "etc/apache/conf.d/cmk_docker.conf"
        apache.write_text(
            "UseCanonicalName Off\nServerName 127.0.0.1\n"
            f"RedirectMatch ^/$ /{site}/\n", encoding="ascii",
        )
        os.chown(apache, 1000, 1000)
        with self._store.transaction(site) as transaction:
            pending_activation = not transaction.load().activation_complete
        if pending_activation:
            if self._backend._run(["/usr/bin/omd", "start", site]).returncode:
                raise BootstrapError("Cannot start the credential-verified site for bootstrap activation.")
            try:
                BootstrapChangeActivation(self._store, self._transport).complete(site)
            finally:
                if self._backend._run(["/usr/bin/omd", "stop", site]).returncode:
                    raise BootstrapError("Cannot stop bootstrap activation runtime; startup blocked.")
        logging.getLogger(__name__).info("STEP PASS: operation=cmk-container-bootstrap site=%s credentials_verified=true", site)


class ContainerBootstrapCli:
    """No passwords in arguments, environment or stdout."""

    def run(self) -> int:
        """Gate container startup without opening any service listener."""
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--site", required=True)
        parser.add_argument("--credential-root", type=Path,
                            default=Path("/var/lib/dwlab/cmk-credentials"))
        args = parser.parse_args()
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S")
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
        logger = logging.getLogger(__package__)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            ContainerSiteBootstrap(SiteCredentialStore(args.credential_root)).configure(args.site)
        except BootstrapError as error:
            logger.error("STEP FAIL: operation=cmk-container-bootstrap reason=%s; startup blocked", error)
            return 1
        except (OSError, ValueError, KeyError) as error:
            logger.error("STEP FAIL: operation=cmk-container-bootstrap failure=%s; startup blocked", type(error).__name__)
            return 1
        return 0
