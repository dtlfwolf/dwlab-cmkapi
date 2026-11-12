from pathlib import Path
import pytest

from dwlabcmkapi.config import LocalApiConnectionPolicy, load_central_server_config
from dwlabcmkapi.api_credentials import Version
from dwlabcmkapi.settings_paths import (
    DEFAULT_SETTINGS_CANDIDATES,
    resolve_central_server_settings_file,
)


def _fake_version(api_version="2.3"):
    return Version(
        site="prod",
        group="dwlab",
        rest_api={"revision": api_version},
        versions={"checkmk": "2.4.0p1"},
        edition="enterprise",
        demo=False,
    )


@pytest.mark.parametrize("local_api,target", [(False, None), (True, "127.0.0.1")])
def test_load_central_server_config_builds_server_and_credentials(monkeypatch, local_api, target):
    class FakeEnv:
        dwlab_package_home = "/opt/dwlab/dwlab-cmkcentralserver"

    class FakeSettings:
        def get_variable(self, key):
            values = {
                "centralHostname": "cmk",
                "centralDomain": "dwlab.local",
                "cmkSite": "central",
                "ovpnNetwork": "vpn",
                "ovpnNetworkDomain": "example",
                "cmkadmin_username": "",
                "cmkadmin_password": "pw",
                "cmkLocalApiAddress": None,
            }
            return values[key]

    from dwlabcmkapi import config

    monkeypatch.setattr(config, "dwlabRuntimeEnvironment", lambda: FakeEnv())
    monkeypatch.setattr(config.dwlabSettings, "read_yaml", lambda path: FakeSettings())
    monkeypatch.setattr(Version, "getVersion", classmethod(lambda cls, cmk_access: _fake_version()))

    result = load_central_server_config(local_api=local_api)

    assert result.settings_file == Path("/opt/dwlab/dwlab-cmkcentralserver/etc/dw-lab_InstallationSettings.yaml")
    assert result.server.site_name == "central"
    assert result.server.fqdn == "cmk.dwlab.local"
    assert result.server.managed_host_name("client01") == "client01.vpn.example"
    assert result.credentials.username == "cmkadmin"
    assert result.credentials.get_apiUrl() == "https://cmk.dwlab.local/central/check_mk/api/2.3"
    assert result.credentials.connection_address == target


@pytest.mark.parametrize("address", ["127.0.0.1", "::1"])
def test_local_policy_accepts_ipv4_and_ipv6_loopback(address):
    assert LocalApiConnectionPolicy(address).address == address


@pytest.mark.parametrize("address", ["localhost", "10.8.0.1", "0.0.0.0", ""])
def test_local_policy_rejects_non_loopback_or_non_literal_addresses(address):
    with pytest.raises(ValueError):
        LocalApiConnectionPolicy(address)


def test_resolve_central_server_settings_file_prefers_explicit_path():
    explicit = Path("/tmp/custom-settings.yaml")

    result = resolve_central_server_settings_file(explicit)

    assert result == explicit


def test_resolve_central_server_settings_file_prefers_existing_primary_candidate(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: self == DEFAULT_SETTINGS_CANDIDATES[0])

    result = resolve_central_server_settings_file()

    assert result == DEFAULT_SETTINGS_CANDIDATES[0]


def test_resolve_central_server_settings_file_uses_existing_secondary_candidate(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: self == DEFAULT_SETTINGS_CANDIDATES[1])

    result = resolve_central_server_settings_file()

    assert result == DEFAULT_SETTINGS_CANDIDATES[1]


def test_resolve_central_server_settings_file_defaults_to_primary_candidate_when_missing(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: False)

    result = resolve_central_server_settings_file()

    assert result == DEFAULT_SETTINGS_CANDIDATES[0]
