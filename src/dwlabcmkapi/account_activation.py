"""Activate only the journal entries acknowledged by account provisioning."""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
import os
from pathlib import Path
import time
from uuid import UUID
from typing import Callable, TYPE_CHECKING

from .bootstrap_changes import BootstrapChangeLedger
from .credential_bootstrap import BootstrapAuthorization, BootstrapError, RootBootstrapAuthorization, SiteCredentialStore

if TYPE_CHECKING:
    from .account_bootstrap import AccountTransport


class BootstrapChangeActivation:
    """Use emergency authorization for a pinned bootstrap batch, never arbitrary foreign changes."""

    def __init__(self, store: SiteCredentialStore, transport: AccountTransport,
                 authorization: BootstrapAuthorization | None = None,
                 logger: logging.Logger | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._store, self._transport = store, transport
        self._authorization = authorization or RootBootstrapAuthorization()
        self._logger = logger or logging.getLogger(__name__)
        self._clock, self._sleep = clock, sleep

    def complete(self, site: str, timeout: float = 300) -> None:
        """Pin ETag and target site, persist the run UUID, then require verified success."""
        caller = os.geteuid()
        self._logger.info("STEP START: operation=cmk-bootstrap-activation caller_uid=%s site=%r", caller, site)
        try:
            self._authorization.require_root()
            self._complete_authorized(site, timeout)
        except (BootstrapError, OSError, ValueError, TypeError) as error:
            self._logger.error("STEP FAIL: operation=cmk-bootstrap-activation caller_uid=%s site=%r failure=%s",
                               caller, site, type(error).__name__)
            raise
        self._logger.info("STEP PASS: operation=cmk-bootstrap-activation caller_uid=%s site=%r", caller, site)

    def _complete_authorized(self, site: str, timeout: float) -> None:
        with self._store.transaction(site) as transaction:
            state = transaction.load()
            if state is None or state.phase != "accounts-ready":
                raise BootstrapError("Account proofs must complete before bootstrap activation.")
            self._transport.verify_identity(state)
            if state.activation_complete:
                self._logger.info("STEP PASS: operation=cmk-bootstrap-activation site=%s already-complete=true", site)
                return
            if not state.activation_id:
                response, records = BootstrapChangeLedger(self._transport).pending(
                    state, "dwlabcmkadm", state.emergency_password,
                )
                if set(records) != set(state.bootstrap_changes):
                    raise BootstrapError("Pending changes do not match the private bootstrap ledger; manual review required.")
                if not records:
                    transaction.save(replace(state, activation_complete=True))
                    return
                etag = response.get("etag")
                if (not isinstance(etag, str) or not 2 <= len(etag) <= 1024
                        or not etag.startswith('"') or not etag.endswith('"')
                        or any(c in etag for c in "\r\n")):
                    raise BootstrapError("Missing bootstrap activation ETag.")
                result = self._transport.request(
                    state, "dwlabcmkadm", state.emergency_password, "POST",
                    "/domain-types/activation_run/actions/activate-changes/invoke",
                    etag=etag, body={"redirect": False, "sites": [site],
                                     "force_foreign_changes": True},
                )
                if result["status"] != 200:
                    raise BootstrapError("Scoped bootstrap activation was rejected.")
                try:
                    activation_id = str(UUID(result["activation"]["id"]))
                except (ValueError, KeyError, TypeError, AttributeError):
                    raise BootstrapError("Missing or invalid bootstrap activation identity; inspect outcome before retrying.") from None
                state = replace(state, activation_id=activation_id)
                transaction.save(state)
            deadline = self._clock() + timeout
            while True:
                response = self._transport.request(
                    state, "dwlabcmkadm", state.emergency_password, "GET",
                    f"/objects/activation_run/{state.activation_id}",
                )
                status = response.get("activation", {})
                try:
                    matching_identity = isinstance(status, dict) and str(UUID(status.get("id"))) == state.activation_id
                except (ValueError, TypeError, AttributeError):
                    matching_identity = False
                if (response["status"] != 200 or not isinstance(status, dict)
                        or not matching_identity
                        or type(status.get("is_running")) is not bool):
                    raise BootstrapError("Cannot verify the recorded bootstrap activation.")
                if status.get("is_running") is False:
                    results = status.get("status_per_site")
                    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
                        raise BootstrapError("Missing per-site activation result.")
                    selected = [item for item in results if item.get("site") == site]
                    if len(selected) != 1 or selected[0].get("state") != "success":
                        raise BootstrapError("Bootstrap activation failed or was not verified for this site.")
                    transaction.save(replace(state, activation_complete=True))
                    break
                if self._clock() >= deadline:
                    raise BootstrapError("Bootstrap activation timed out; recorded run retained for review/retry.")
                self._sleep(1)
        self._logger.info("STEP PASS: operation=cmk-bootstrap-activation site=%s activation_verified=true", site)


class AccountActivationCli:
    """Independent root-only finalizer; no password arguments or network listener."""

    def run(self, argv: list[str] | None = None) -> int:
        from dwlabbasicpy.dwlabLogging import UtcLogFormatter
        from .account_bootstrap import NativeAccountTransport

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=["complete"])
        parser.add_argument("--site", required=True)
        parser.add_argument("--credential-root", type=Path,
                            default=Path("/var/lib/dwlab/dwlabcmkapi/credentials"))
        parser.add_argument("--run-id")
        args = parser.parse_args(argv)
        logger = logging.Logger("dwlabcmkapi.bootstrap-activation")
        handler = logging.StreamHandler()
        handler.setFormatter(UtcLogFormatter(run_id=args.run_id))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            BootstrapChangeActivation(SiteCredentialStore(args.credential_root),
                                      NativeAccountTransport(), logger=logger).complete(args.site)
        except (BootstrapError, OSError, ValueError) as error:
            logger.error("STEP FAIL: operation=cmk-bootstrap-activation failure=%s; activation not verified", type(error).__name__)
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(AccountActivationCli().run())
