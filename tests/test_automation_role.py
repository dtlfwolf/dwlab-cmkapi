"""Machine accounts must not inherit administrator/user-management permissions."""

import pytest

from dwlabcmkapi.automation_role import AutomationRoleProvisioner
from dwlabcmkapi.credential_bootstrap import BootstrapError, SiteCredentialState
from tests.test_account_bootstrap import FakeTransport


def fixture():
    state = SiteCredentialState.generate("central", 6000, 6000)
    transport = FakeTransport(state)
    return state, transport, AutomationRoleProvisioner(transport)


def test_policy_denies_user_administration_and_unknown_permissions():
    state, transport, policy = fixture()
    policy.assert_absent(state)
    policy.provision(state)
    assert "wato.users" not in transport.role["permissions"]
    assert "wato.sites" in transport.role["permissions"]
    assert transport.role["basedon"] == "user"


def test_preexisting_role_not_adopted():
    state, transport, policy = fixture()
    policy.provision(state)
    with pytest.raises(BootstrapError, match="already exists"):
        policy.assert_absent(state)


@pytest.mark.parametrize("permission", ["wato.users", "new.privilege"])
def test_expanded_role_rejected_on_verification(permission):
    state, transport, policy = fixture()
    policy.provision(state)
    transport.role["permissions"].append(permission)
    with pytest.raises(BootstrapError, match="restricted"):
        policy.verify(state, "cmkadmin", state.bootstrap_password)


def test_missing_required_permission_rejected():
    state, transport, policy = fixture()
    policy.provision(state)
    transport.role["permissions"].remove("wato.sites")
    with pytest.raises(BootstrapError):
        policy.verify(state, "cmkadmin", state.bootstrap_password)
