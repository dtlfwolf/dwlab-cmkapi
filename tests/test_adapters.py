from dwlabcmkapi.api_credentials import RestAPIcredentials
from dwlabcmkapi.gateways import CheckmkGateway


def _credentials_stub():
    credentials = object.__new__(RestAPIcredentials)
    credentials._version = type("VersionStub", (), {"apiVersion": "2.3", "checkmkVersion": "2.4.0p1"})()
    credentials._credentials = "Bearer token"
    credentials._cmkHostname = "cmk"
    credentials._cmkDomain = "dwlab.local"
    credentials._cmkSiteName = "central"
    return credentials


def test_gateway_derives_ovpn_naming_for_site_connection(monkeypatch):
    captured = {}

    class FakeSiteConnection:
        def __init__(self):
            basic_settings = type("BasicSettings", (), {"alias": "", "site_id": ""})()
            connection = type("Connection", (), {"host": ""})()
            status_connection = type("StatusConnection", (), {"connection": connection, "url_prefix": ""})()
            configuration_connection = type(
                "ConfigurationConnection", (), {"url_of_remote_site": ""}
            )()
            class Extensions:
                def __init__(self):
                    self.basic_settings = basic_settings
                    self.status_connection = status_connection
                    self.configuration_connection = configuration_connection

                def to_dict(self):
                    return {}

            self.extensions = Extensions()
            self.id = ""
            self.title = ""

    from dwlabcmkapi import gateways
    from dwlabcmkapi import operations

    monkeypatch.setattr(gateways, "SiteConnection", FakeSiteConnection)
    monkeypatch.setattr(
        operations.SiteConnectionGateway,
        "create_site_connection",
        lambda self, site_connection: captured.update(
            {
                "cmkAccess": self._cmk_access,
                "site_connection": site_connection,
                "path": "/domain-types/site_connection/collections/all",
            }
        ),
    )

    gateway = CheckmkGateway(_credentials_stub())
    gateway.create_site_connection(
        site_id="client01",
        remote_host="client01.vpn.dwlab.example",
        url_prefix="http://client01.vpn.dwlab.example:8080/client01/",
        remote_site_url="http://client01.vpn.dwlab.example:8080/client01/check_mk/",
    )

    assert captured["cmkAccess"] is gateway.cmk_access
    assert captured["path"] == "/domain-types/site_connection/collections/all"
    assert captured["site_connection"].extensions.status_connection.connection.host == "client01.vpn.dwlab.example"
