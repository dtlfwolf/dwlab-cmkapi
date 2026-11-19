"""Journal identities, not translated descriptions, authorize finalization."""

from dataclasses import replace

import pytest

from dwlabcmkapi.bootstrap_changes import BootstrapChangeLedger
from dwlabcmkapi.credential_bootstrap import BootstrapError, SiteCredentialState
from tests.test_account_bootstrap import FakeTransport


def fixture():
    state = SiteCredentialState.generate("central", 6000, 6000)
    transport = FakeTransport(state)
    return state, transport, BootstrapChangeLedger(transport)


def test_only_one_acknowledged_user_change_is_recorded():
    state, transport, ledger = fixture()
    transport.changes = [{"id": "change", "action_name": "edit-users", "user_id": "cmkadmin"}]
    recorded = ledger.record_one(state, "cmkadmin", state.bootstrap_password)
    assert len(recorded.bootstrap_changes) == 1
    transport.changes[0].update(text="Translated description", time="different display timezone")
    ledger.assert_current(recorded, "cmkadmin", state.bootstrap_password)


@pytest.mark.parametrize("action,actor", [("edit-host", "cmkadmin"), ("edit-users", "customer")])
def test_other_actions_and_actors_are_not_adopted(action, actor):
    state, transport, ledger = fixture()
    transport.changes = [{"id": "change", "action_name": action, "user_id": actor}]
    with pytest.raises(BootstrapError, match="could not be attributed"):
        ledger.record_one(state, "cmkadmin", state.bootstrap_password)


def test_concurrent_extra_changes_are_not_adopted():
    state, transport, ledger = fixture()
    transport.changes = [{"id": str(index), "action_name": "edit-users", "user_id": "cmkadmin"} for index in range(2)]
    with pytest.raises(BootstrapError):
        ledger.record_one(state, "cmkadmin", state.bootstrap_password)
