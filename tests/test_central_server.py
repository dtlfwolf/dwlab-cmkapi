import pytest

from dwlabcmkapi.api_credentials import RestAPIcredentials
from dwlabcmkapi.central_server import CentralServerManager


def _credentials_stub():
    credentials = object.__new__(RestAPIcredentials)
    credentials._version = type("VersionStub", (), {"apiVersion": "2.3", "checkmkVersion": "2.4.0p1"})()
    credentials._credentials = "Bearer token"
    credentials._cmkHostname = "cmk"
    credentials._cmkDomain = "dwlab.local"
    credentials._cmkSiteName = "central"
    return credentials


def test_central_server_manager_exposes_constructor_values():
    site = CentralServerManager(
        site_name="central",
        hostname="cmk",
        domain="dwlab.local",
        ovpn_network="vpn",
        ovpn_network_domain="example",
        credentials=_credentials_stub(),
    )

    assert site.site_name == "central"
    assert site.hostname == "cmk"
    assert site.domain == "dwlab.local"
    assert site.ovpn_network == "vpn"
    assert site.ovpn_network_domain == "example"
    assert site.api_version == "2.3"
    assert site.checkmk_version == "2.4.0p1"


def test_central_server_manager_requires_rest_api_credentials():
    with pytest.raises(TypeError, match="credentials must be an instance of RestAPIcredentials"):
        CentralServerManager(
            site_name="central",
            hostname="cmk",
            domain="dwlab.local",
            ovpn_network="vpn",
            ovpn_network_domain="example",
            credentials=object(),
        )
