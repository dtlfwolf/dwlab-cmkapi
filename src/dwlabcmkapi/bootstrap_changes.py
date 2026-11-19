"""A private ledger of changes created by stopped-site account provisioning."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import TYPE_CHECKING

from .credential_bootstrap import BootstrapError, SiteCredentialState

if TYPE_CHECKING:
    from .account_bootstrap import AccountTransport


class BootstrapChangeLedger:
    """Reject pre-existing/concurrent changes rather than forcing a customer's work."""

    PATH = "/domain-types/activation_run/collections/pending_changes"

    def __init__(self, transport: AccountTransport) -> None:
        self._transport = transport

    def pending(self, state: SiteCredentialState, actor: str, secret: str) -> tuple[dict, dict[str, dict]]:
        """Return opaque fingerprints; never log free-text change descriptions."""
        response = self._transport.request(state, actor, secret, "GET", self.PATH)
        changes = response.get("pending_changes")
        if response["status"] != 200 or not isinstance(changes, list):
            raise BootstrapError("Cannot inspect pending changes before scoped bootstrap activation.")
        records = {}
        for change in changes:
            if (not isinstance(change, dict) or any(not isinstance(change.get(key), str)
                    for key in ("id", "action_name", "user_id"))):
                raise BootstrapError("Invalid pending-change identity.")
            identity = {key: change[key] for key in ("id", "action_name", "user_id")}
            # Display text/timestamps can depend on the authenticated user's locale.
            fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if fingerprint in records:
                raise BootstrapError("Duplicate pending-change identity.")
            records[fingerprint] = change
        return response, records

    def assert_current(self, state: SiteCredentialState, actor: str, secret: str) -> None:
        """Require exactly the recorded changes; a stopped site is the maintenance boundary."""
        _, records = self.pending(state, actor, secret)
        if set(records) != set(state.bootstrap_changes):
            raise BootstrapError("Unrecorded pending changes require review before account provisioning/activation.")

    def record_one(self, state: SiteCredentialState, actor: str, secret: str) -> SiteCredentialState:
        """Accept one acknowledged user mutation, never an unrelated batch of changes."""
        _, records = self.pending(state, actor, secret)
        old = set(state.bootstrap_changes)
        difference = set(records) - old
        if (not old.issubset(records) or len(difference) != 1
                or records[next(iter(difference))].get("action_name") != "edit-users"
                or records[next(iter(difference))].get("user_id") != actor):
            raise BootstrapError("Account change could not be attributed; retain recovery state for review.")
        return replace(state, bootstrap_changes=tuple(sorted(records)))
