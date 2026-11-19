"""Verify independent site accounts before retiring the bootstrap identity."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import logging
import os
from pathlib import Path
import pwd
import shlex
import subprocess
from typing import Callable, Protocol

from .credential_bootstrap import (
    BootstrapAuthorization, BootstrapError, OmdBootstrapBackend,
    RootBootstrapAuthorization, SiteCredentialState, SiteCredentialStore,
)
from .automation_role import AutomationRoleProvisioner
from .bootstrap_changes import BootstrapChangeLedger


class AccountTransport(Protocol):
    """Authenticated site-local requests; implementations must not open listeners."""

    def verify_site(self, state: SiteCredentialState) -> None: ...
    def verify_identity(self, state: SiteCredentialState) -> None: ...

    def request(self, state: SiteCredentialState, username: str, password: str,
                method: str, path: str, *, body: dict | None = None,
                etag: str | None = None) -> dict: ...


class NativeAccountTransport:
    """Invoke the installed WSGI adapter with site Python and stdin secrets."""

    def __init__(self, runner: Callable = subprocess.run,
                 authorization: BootstrapAuthorization | None = None) -> None:
        self._runner = runner
        self._authorization = authorization or RootBootstrapAuthorization()
        self._omd = OmdBootstrapBackend(runner=runner, authorization=self._authorization)

    def verify_site(self, state: SiteCredentialState) -> None:
        """Require a supported stopped site with the recorded OS identity."""
        self.verify_identity(state)
        if not self._omd.is_stopped(state.site):
            raise BootstrapError("Account provisioning requires the recorded site to exist and be stopped.")

    def verify_identity(self, state: SiteCredentialState) -> None:
        """Check a recorded site's OS identity, including during online activation."""
        self._authorization.require_root()
        self._omd.verify_support()
        if not self._omd.exists(state.site):
            raise BootstrapError("The recorded site is missing.")
        account = pwd.getpwnam(state.site)
        if (account.pw_uid, account.pw_gid) != (state.uid, state.gid):
            raise BootstrapError("Site OS identity differs from private preparation state.")

    def request(self, state: SiteCredentialState, username: str, password: str,
                method: str, path: str, *, body: dict | None = None,
                etag: str | None = None) -> dict:
        """Return sanitized metadata only; do not propagate secret-bearing errors."""
        self._authorization.require_root()
        program = Path(__file__).with_name("native_account_runner.py").read_text()
        arguments = [
            "/usr/sbin/runuser", "--login", state.site, "--command",
            shlex.join(["python3", "-c", program]),
        ]
        payload = {"site": state.site, "username": username, "password": password,
                   "method": method, "path": path, "body": body, "etag": etag,
                   "legacy_migration": state.legacy_migration}
        try:
            result = self._runner(
                arguments, input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, check=False, timeout=120,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
            )
            if len(result.stdout) > 131072:
                raise ValueError
            data = json.loads(result.stdout)
            if result.returncode:
                code = data.get("error") if isinstance(data, dict) else None
                if code in {"native-filesystem-permission-denied", "native-dependency-unavailable"}:
                    raise BootstrapError(f"Native account operation failed ({code}); sensitive diagnostics suppressed.")
                raise ValueError
            if not isinstance(data, dict) or type(data.get("status")) is not int:
                raise ValueError
            return data
        except (OSError, ValueError, subprocess.SubprocessError):
            raise BootstrapError("Native account operation failed; sensitive diagnostics suppressed.") from None


class SiteAccountProvisioner:
    """Use Checkmk's authenticated user-management API, not direct config writes."""

    ADMIN = "dwlabcmkadm"
    AUTOMATION = "dwlab-automation"

    def __init__(self, transport: AccountTransport) -> None:
        self._transport = transport

    def _get(self, state: SiteCredentialState, account: str,
             actor: str, secret: str) -> dict:
        return self._transport.request(state, actor, secret, "GET", f"/objects/user_config/{account}")

    def assert_absent(self, state: SiteCredentialState) -> None:
        """Refuse unexpected existing accounts before recording mutation intent."""
        for account in (self.ADMIN, self.AUTOMATION):
            if self._get(state, account, "cmkadmin", state.bootstrap_password)["status"] != 404:
                raise BootstrapError("Replacement account preflight failed; existing accounts are not overwritten.")
        AutomationRoleProvisioner(self._transport).assert_absent(state)
        BootstrapChangeLedger(self._transport).assert_current(state, "cmkadmin", state.bootstrap_password)
        connections = self._transport.request(
            state, "cmkadmin", state.bootstrap_password, "GET",
            "/domain-types/site_connection/collections/all",
        )
        if (connections["status"] != 200 or not isinstance(connections.get("site_connections"), list)
                or any(item.get("id") != state.site and item.get("replication_enabled") is not False
                       for item in connections["site_connections"])):
            raise BootstrapError("Independent local accounts require configuration/user replication to be disabled.")

    def _verify_one(self, state: SiteCredentialState, account: str, secret: str,
                    auth_type: str) -> None:
        actor = self.ADMIN if account == self.AUTOMATION else account
        actor_secret = state.emergency_password if account == self.AUTOMATION else secret
        response = self._get(state, account, actor, actor_secret)
        user = response.get("user", {})
        roles = [AutomationRoleProvisioner.NAME] if account == self.AUTOMATION else ["admin"]
        if (response["status"] != 200 or not isinstance(user, dict) or user.get("id") != account
                or user.get("roles") != roles or user.get("disabled") is not False
                or user.get("auth_type") != auth_type
                or (auth_type == "automation" and user.get("store_secret") is not False)):
            raise BootstrapError(f"Independent administrative authentication failed for {account}.")
        if account == self.AUTOMATION:
            proof = self._transport.request(state, account, secret, "GET", "/version")
            denied = self._get(state, self.ADMIN, account, secret)
            if proof["status"] != 200 or denied["status"] not in {401, 403}:
                raise BootstrapError("Automation authentication or privilege separation failed.")

    def provision(self, state: SiteCredentialState, checkpoint: Callable) -> SiteCredentialState:
        """Create missing accounts; retry only accounts with our verified secrets."""
        ledger = BootstrapChangeLedger(self._transport)
        ledger.assert_current(state, "cmkadmin", state.bootstrap_password)
        AutomationRoleProvisioner(self._transport).provision(state)
        ledger.assert_current(state, "cmkadmin", state.bootstrap_password)
        for account, secret, auth_type in (
            (self.ADMIN, state.emergency_password, "password"),
            (self.AUTOMATION, state.automation_secret, "automation"),
        ):
            current = self._get(state, account, "cmkadmin", state.bootstrap_password)
            if current["status"] == 404:
                auth = {"auth_type": auth_type}
                if auth_type == "password":
                    auth.update(password=secret, enforce_password_change=False)
                else:
                    auth.update(secret=secret, store_automation_secret=False)
                response = self._transport.request(
                    state, "cmkadmin", state.bootstrap_password, "POST",
                    "/domain-types/user_config/collections/all",
                    body={"username": account, "fullname": f"DW-Lab local {account}",
                          "roles": ([AutomationRoleProvisioner.NAME] if account == self.AUTOMATION
                                    else ["admin"]),
                          "disable_login": False, "auth_option": auth},
                )
                if response["status"] != 200:
                    raise BootstrapError(f"Account creation failed for {account}; no credential overwrite attempted.")
                state = ledger.record_one(state, "cmkadmin", state.bootstrap_password)
                checkpoint(state)
            elif current["status"] != 200:
                raise BootstrapError(f"Account inspection failed for {account}.")
            self._verify_one(state, account, secret, auth_type)
        return state

    def verify_replacements(self, state: SiteCredentialState) -> None:
        """Authenticate each replacement separately, never through bootstrap cookies."""
        self._verify_one(state, self.ADMIN, state.emergency_password, "password")
        AutomationRoleProvisioner(self._transport).verify(state, self.ADMIN, state.emergency_password)
        self._verify_one(state, self.AUTOMATION, state.automation_secret, "automation")

    def retire_bootstrap(self, state: SiteCredentialState, checkpoint: Callable) -> SiteCredentialState:
        """Disable/remove bootstrap authentication only after replacement proofs."""
        self.verify_replacements(state)
        ledger = BootstrapChangeLedger(self._transport)
        ledger.assert_current(state, self.ADMIN, state.emergency_password)
        current = self._get(state, "cmkadmin", self.ADMIN, state.emergency_password)
        user = current.get("user")
        if current["status"] != 200 or not isinstance(user, dict):
            raise BootstrapError("Cannot inspect bootstrap account through the emergency administrator.")
        if user.get("disabled") is not True:
            etag = current.get("etag")
            if not isinstance(etag, str) or not etag or len(etag) > 1024 or any(c in etag for c in "\r\n"):
                raise BootstrapError("Missing or invalid bootstrap account ETag.")
            response = self._transport.request(
                state, self.ADMIN, state.emergency_password, "PUT",
                "/objects/user_config/cmkadmin", etag=etag,
                body={"disable_login": True, "auth_option": {"auth_type": "remove"}},
            )
            if response["status"] != 200:
                raise BootstrapError("Bootstrap retirement failed; private recovery state retained.")
            state = ledger.record_one(state, self.ADMIN, state.emergency_password)
            checkpoint(state)
        self.verify_retired(state)
        if state.bootstrap_password:
            denied = self._get(state, "cmkadmin", "cmkadmin", state.bootstrap_password)
            if denied["status"] not in {401, 403}:
                raise BootstrapError("Old bootstrap credential was not conclusively rejected.")
        return state

    def verify_retired(self, state: SiteCredentialState) -> None:
        """Verify both permanent accounts and the disabled bootstrap account."""
        self.verify_replacements(state)
        current = self._get(state, "cmkadmin", self.ADMIN, state.emergency_password)
        user = current.get("user")
        if (current["status"] != 200 or not isinstance(user, dict)
                or user.get("disabled") is not True):
            raise BootstrapError("Bootstrap account is not verified disabled.")


@dataclass(frozen=True)
class AccountCompletionResult:
    """Credential prerequisite only; this command does not activate any service."""

    site: str
    phase: str = "accounts-ready"
    credential_gate_passed: bool = True
    activation_performed: bool = False


class SiteAccountCompletion:
    """Persist safe retry boundaries and remove retired bootstrap material."""

    def __init__(self, store: SiteCredentialStore, transport: AccountTransport,
                 authorization: BootstrapAuthorization | None = None,
                 logger: logging.Logger | None = None) -> None:
        self._store, self._transport = store, transport
        self._authorization = authorization or RootBootstrapAuthorization()
        self._logger = logger or logging.getLogger(__name__)

    def complete(self, site: str) -> AccountCompletionResult:
        """Leave autostart disabled; never retire bootstrap on an unverified result."""
        caller = os.geteuid()
        self._logger.info("STEP START: operation=cmk-account-complete caller_uid=%s site=%r", caller, site)
        try:
            self._authorization.require_root()
            with self._store.transaction(site) as transaction:
                state = transaction.load()
                if state is None or state.phase not in {
                    "awaiting-accounts", "provisioning-accounts", "retiring-bootstrap", "accounts-ready",
                }:
                    raise BootstrapError("Site has not completed private credential preparation.")
                self._transport.verify_site(state)
                accounts = SiteAccountProvisioner(self._transport)
                if state.phase == "awaiting-accounts":
                    accounts.assert_absent(state)
                    state = replace(state, phase="provisioning-accounts")
                    transaction.save(state)
                if state.phase == "provisioning-accounts":
                    state = accounts.provision(state, transaction.save)
                    state = replace(state, phase="retiring-bootstrap")
                    transaction.save(state)
                    self._logger.info("STEP PASS: operation=cmk-account-complete phase=replacements-verified site=%s", site)
                if state.phase == "retiring-bootstrap":
                    state = accounts.retire_bootstrap(state, transaction.save)
                    state = replace(state, phase="accounts-ready", bootstrap_password="")
                    transaction.save(state)
                accounts.verify_retired(state)
        except (BootstrapError, OSError, KeyError, TypeError, ValueError) as error:
            self._logger.error("STEP FAIL: operation=cmk-account-complete caller_uid=%s site=%r failure=%s", caller, site, type(error).__name__)
            raise BootstrapError("Account completion failed; private recovery state retained and activation blocked.") from None
        self._logger.info("STEP PASS: operation=cmk-account-complete caller_uid=%s site=%r phase=accounts-ready activation_performed=false", caller, site)
        return AccountCompletionResult(site)


class AccountBootstrapCli:
    """Root-only entry point; accepts no caller-supplied account passwords."""

    def run(self, argv: list[str] | None = None) -> int:
        """Complete accounts on an explicitly prepared stopped site."""
        from dwlabbasicpy.dwlabLogging import UtcLogFormatter

        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=["complete-accounts"])
        parser.add_argument("--site", required=True)
        parser.add_argument("--run-id")
        parser.add_argument("--credential-root", type=Path,
                            default=Path("/var/lib/dwlab/dwlabcmkapi/credentials"))
        args = parser.parse_args(argv)
        logger = logging.Logger("dwlabcmkapi.account-bootstrap")
        handler = logging.StreamHandler()
        handler.setFormatter(UtcLogFormatter(run_id=args.run_id))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            result = SiteAccountCompletion(
                SiteCredentialStore(args.credential_root), NativeAccountTransport(), logger=logger,
            ).complete(args.site)
        except BootstrapError as error:
            logger.error("STEP FAIL: %s", error)
            return 1
        print(json.dumps(vars(result)))
        return 0


if __name__ == "__main__":
    raise SystemExit(AccountBootstrapCli().run())
