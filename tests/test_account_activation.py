"""Only acknowledged bootstrap changes may use emergency activation rights."""

from dataclasses import replace

import pytest

from dwlabcmkapi.account_activation import BootstrapChangeActivation
from dwlabcmkapi.credential_bootstrap import BootstrapError
from dwlabcmkapi.credential_provider import SiteAutomationCredentialProvider
from tests.test_account_bootstrap import TestAccountCompletion as AccountCompletionFixture
from tests.test_credential_bootstrap import TestAuthorization


class ActivationTransport:
    ID = "7eb3dbf2-c450-4ca5-9e22-b0c0854f2570"

    def __init__(self, base):
        self.base = base
        self.posts = []
        self.failure = False
        self.results = [{"site": "central", "state": "success"}]

    def verify_identity(self, state):
        pass

    def request(self, state, username, password, method, path, *, body=None, etag=None):
        if "activation_run" not in path or path.endswith("pending_changes"):
            return self.base.request(state, username, password, method, path, body=body, etag=etag)
        assert username == "dwlabcmkadm"
        assert password == state.emergency_password
        if method == "POST":
            assert etag == self.base.etag
            assert body == {"redirect": False, "sites": ["central"], "force_foreign_changes": True}
            self.posts.append(body)
            self.base.changes.clear()
            return {"status": 200, "activation": {"id": self.ID}}
        if self.failure:
            return {"status": 500}
        return {"status": 200, "activation": {"id": self.ID, "is_running": False,
                                               "status_per_site": self.results}}


def fixture(tmp_path):
    store, _, base, completion = AccountCompletionFixture().fixture(tmp_path)
    completion.complete("central")
    transport = ActivationTransport(base)
    service = BootstrapChangeActivation(store, transport, TestAuthorization())
    return store, base, transport, service


def test_credentials_are_not_ready_until_scoped_activation_succeeds(tmp_path):
    store, _, transport, service = fixture(tmp_path)
    provider = SiteAutomationCredentialProvider(TestAuthorization())
    reference = store.root / "central/credentials.json"
    assert provider.find_ready(reference, "central") is None
    service.complete("central")
    assert provider.resolve(reference, "central").username == "dwlab-automation"
    assert len(transport.posts) == 1


def test_unrelated_pending_changes_are_never_forced(tmp_path):
    store, base, transport, service = fixture(tmp_path)
    base.changes.append({"id": "customer", "action_name": "edit-host", "user_id": "customer"})
    with pytest.raises(BootstrapError, match="private bootstrap ledger"):
        service.complete("central")
    assert not transport.posts
    with store.transaction("central") as transaction:
        assert not transaction.load().activation_complete


def test_completed_retry_does_not_activate_later_customer_work(tmp_path):
    _, base, transport, service = fixture(tmp_path)
    service.complete("central")
    base.changes.append({"id": "customer", "action_name": "edit-host", "user_id": "customer"})
    service.complete("central")
    assert len(transport.posts) == 1
    assert len(base.changes) == 1


def test_poll_failure_retains_run_for_safe_retry_without_duplicate_activation(tmp_path):
    store, _, transport, service = fixture(tmp_path)
    transport.failure = True
    with pytest.raises(BootstrapError):
        service.complete("central")
    with store.transaction("central") as transaction:
        state = transaction.load()
    assert state.activation_id == transport.ID
    assert not state.activation_complete
    transport.failure = False
    service.complete("central")
    assert len(transport.posts) == 1


@pytest.mark.parametrize("results", [[], [{"site": "other", "state": "success"}],
                                   [{"site": "central", "state": "error"}]])
def test_failed_or_missing_target_site_never_reports_success(tmp_path, results):
    store, _, transport, service = fixture(tmp_path)
    transport.results = results
    with pytest.raises(BootstrapError, match="failed or was not verified"):
        service.complete("central")
    with store.transaction("central") as transaction:
        assert not transaction.load().activation_complete


def test_completed_accounts_without_a_ledger_do_not_adopt_unknown_changes(tmp_path):
    store, _, transport, service = fixture(tmp_path)
    with store.transaction("central") as transaction:
        transaction.save(replace(transaction.load(), bootstrap_changes=()))
    with pytest.raises(BootstrapError):
        service.complete("central")
    assert not transport.posts


def test_unauthorized_finalization_is_denied_and_audited(tmp_path, caplog):
    store, _, transport, _ = fixture(tmp_path)

    class Denied:
        def require_root(self):
            raise BootstrapError("Root authorization required")

    with pytest.raises(BootstrapError, match="Root authorization"):
        BootstrapChangeActivation(store, transport, Denied()).complete("central")
    assert not transport.posts
    assert "STEP FAIL: operation=cmk-bootstrap-activation caller_uid=" in caplog.text
