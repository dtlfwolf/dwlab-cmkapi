"""Private credential references must not weaken installation boundaries."""

from dataclasses import replace

import pytest

from dwlabcmkapi.credential_bootstrap import (
    BootstrapError, SiteCredentialState, SiteCredentialStore,
)
from dwlabcmkapi.credential_provider import (
    SettingsCredentialResolver, SiteAutomationCredentialProvider,
)


class Allowed:
    def require_root(self):
        pass


class Denied:
    def require_root(self):
        raise BootstrapError("denied")


class Settings:
    def __init__(self, **values):
        self.values = values

    def get_variable(self, variableName):
        return self.values.get(variableName)


@pytest.fixture
def ready(tmp_path):
    root = tmp_path / "private"
    state = replace(SiteCredentialState.generate("central", 6000, 6000),
                    phase="accounts-ready", bootstrap_password="")
    with SiteCredentialStore(root).transaction("central") as transaction:
        transaction.save(state)
    return root / "central" / "credentials.json", state


def test_ready_reference_returns_automation_only(ready):
    path, state = ready
    credential = SiteAutomationCredentialProvider(Allowed()).resolve(path, "central")
    assert credential.username == "dwlab-automation"
    assert credential.secret == state.automation_secret
    assert state.automation_secret not in repr(credential)
    assert state.emergency_password not in repr(credential)


def test_reference_requires_os_authorization(ready):
    with pytest.raises(BootstrapError, match="denied"):
        SiteAutomationCredentialProvider(Denied()).resolve(ready[0], "central")


@pytest.mark.parametrize("path", ["relative", "/tmp/other/credentials.json", "/tmp/central/state.json",
                                 "/tmp/../central/credentials.json"])
def test_invalid_references_rejected(path):
    with pytest.raises(BootstrapError):
        SiteAutomationCredentialProvider(Allowed()).resolve(path, "central")


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o400])
def test_unsafe_file_modes_rejected(ready, mode):
    path, _ = ready
    path.chmod(mode)
    with pytest.raises(BootstrapError):
        SiteAutomationCredentialProvider(Allowed()).resolve(path, "central")


def test_symlink_reference_rejected(ready):
    path, _ = ready
    original = path.with_name("original.json")
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(OSError):
        SiteAutomationCredentialProvider(Allowed()).resolve(path, "central")


@pytest.mark.parametrize("phase", ["prepared", "awaiting-accounts", "retiring-bootstrap"])
def test_incomplete_state_rejected(ready, phase):
    path, _ = ready
    with SiteCredentialStore(path.parent.parent).transaction("central") as transaction:
        transaction.save(replace(SiteCredentialState.generate("central", 6000, 6000), phase=phase))
    with pytest.raises(BootstrapError, match="not ready"):
        SiteAutomationCredentialProvider(Allowed()).resolve(path, "central")


def test_reference_failure_never_falls_back_to_legacy(tmp_path, caplog):
    settings = Settings(cmkCredentialsFile=str(tmp_path / "central" / "credentials.json"),
                        cmkadmin_password="legacy-secret")
    with pytest.raises(BootstrapError, match="not ready"):
        SettingsCredentialResolver(SiteAutomationCredentialProvider(Allowed())).resolve(settings, "central")
    assert "legacy-secret" not in caplog.text
    assert "Legacy" not in caplog.text


def test_legacy_is_explicitly_reported_without_secret(caplog):
    result = SettingsCredentialResolver().resolve(Settings(cmkadmin_password="old-secret"), "central")
    assert result.username == "cmkadmin"
    assert result.secret == "old-secret"
    assert "migration is required" in caplog.text
    assert "old-secret" not in caplog.text


@pytest.mark.parametrize("secret", [None, "", "bad\nheader", "bad\x00value"])
def test_missing_or_invalid_legacy_credentials_rejected(secret):
    with pytest.raises(BootstrapError):
        SettingsCredentialResolver().resolve(Settings(cmkadmin_password=secret), "central")


@pytest.mark.parametrize("loader", ["config", "from-file"])
def test_public_loaders_resolve_private_reference(ready, monkeypatch, loader):
    from dwlabcmkapi import api_credentials, config

    path, state = ready
    settings = Settings(cmkCredentialsFile=str(path), cmkSite="central",
                        centralHostname="cmk", centralDomain="example.test",
                        ovpnNetwork="vpn", ovpnNetworkDomain="example.test")
    provider = SiteAutomationCredentialProvider(Allowed())
    monkeypatch.setattr(config, "dwlabRuntimeEnvironment", lambda: object())
    monkeypatch.setattr(config.dwlabSettings, "read_yaml", lambda _: settings)
    monkeypatch.setattr(api_credentials.Version, "getVersion", classmethod(lambda cls, _: None))
    monkeypatch.setattr(config, "SettingsCredentialResolver", lambda: SettingsCredentialResolver(provider))
    monkeypatch.setattr(api_credentials, "SettingsCredentialResolver", lambda: SettingsCredentialResolver(provider))
    if loader == "config":
        result = config.load_central_server_config(local_api=True).credentials
        assert result.connection_address == "127.0.0.1"
    else:
        result = api_credentials.RestAPIcredentials.fromFile("ignored.yaml")
    assert result.username == "dwlab-automation"
    assert result.credentials == f"Bearer dwlab-automation {state.automation_secret}"
