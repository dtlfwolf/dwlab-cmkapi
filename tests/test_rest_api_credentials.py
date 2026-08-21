import pytest

from dwlabcmkapi.api_client import CheckmkRestClient
from dwlabcmkapi.api_credentials import RestAPIcredentials, Version


def _fake_version(api_version="2.3"):
    return Version(
        site="prod",
        group="dwlab",
        rest_api={"revision": api_version},
        versions={"checkmk": "2.4.0p1"},
        edition="enterprise",
        demo=False,
    )


def test_rest_api_credentials_builds_bearer_token(monkeypatch):
    monkeypatch.setattr(Version, "getVersion", classmethod(lambda cls, cmk_access: _fake_version()))

    credentials = RestAPIcredentials(
        cmkHostname="central",
        cmkDomain="example.org",
        cmkSiteName="main",
        username="api-user",
        password="secret",
    )

    assert credentials.credentials == "Bearer api-user secret"
    assert credentials.get_apiUrl() == "https://central.example.org/main/check_mk/api/2.3"


def test_rest_api_credentials_requires_authentication(monkeypatch):
    monkeypatch.setattr(Version, "getVersion", classmethod(lambda cls, cmk_access: _fake_version()))

    with pytest.raises(ValueError, match="Username and password must be provided"):
        RestAPIcredentials(cmkHostname="central", cmkDomain="example.org", cmkSiteName="main")


def test_rest_api_credentials_from_file_uses_dwlab_settings(monkeypatch):
    monkeypatch.setattr(Version, "getVersion", classmethod(lambda cls, cmk_access: _fake_version("1.0")))

    class FakeSettings:
        def get_variable(self, key):
            values = {
                "cmkSite": "central",
                "cmkadmin_username": "",
                "cmkadmin_password": "pw",
                "centralHostname": "cmk",
                "centralDomain": "dwlab.local",
            }
            return values[key]

    from dwlabcmkapi import api_credentials

    monkeypatch.setattr(api_credentials.dwlabSettings, "read_yaml", lambda path: FakeSettings())

    credentials = RestAPIcredentials.fromFile(configFile="ignored.yaml")

    assert credentials.username == "cmkadmin"
    assert credentials.credentials == "Bearer cmkadmin pw"
    assert credentials.get_apiUrl() == "https://cmk.dwlab.local/central/check_mk/api/1.0"


def test_rest_api_credentials_exposes_compat_site_alias_and_client(monkeypatch):
    monkeypatch.setattr(Version, "getVersion", classmethod(lambda cls, cmk_access: _fake_version("2.3")))

    credentials = RestAPIcredentials(
        cmkHostname="central",
        cmkDomain="example.org",
        cmkSiteName="main",
        username="api-user",
        password="secret",
    )

    client = credentials.create_client("1.0.0")

    assert credentials.cmkSite == "main"
    assert isinstance(client, CheckmkRestClient)
    assert client.base_url == "https://central.example.org/main/check_mk/api/1.0.0"
