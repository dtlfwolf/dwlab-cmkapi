"""Status-only connections remain independent across the 2.4/2.5 API schemas."""

from types import SimpleNamespace

import pytest

from dwlabcmkapi import api_credentials
from dwlabcmkapi.api_credentials import RestAPIcredentials
from dwlabcmkapi.api_site_connections import ConfigurationConnection, SiteConnection
from dwlabcmkapi.operations import SiteConnectionGateway


@pytest.mark.parametrize("version", ["2.4.0p35.cre", "2.5.0p11.community"])
@pytest.mark.parametrize("operation", ["create_site_connection", "update_site_connection"])
def test_gateway_uses_its_own_target_version_not_global_metadata(monkeypatch, version, operation):
    monkeypatch.setattr(api_credentials, "VERSION", SimpleNamespace(checkmk_version="2.2.0p1"))
    calls = []

    def request(path, **kwargs):
        calls.append(kwargs["json_body"]["site_config"]["configuration_connection"])
        return SimpleNamespace(status_code=200)

    credential = RestAPIcredentials.__new__(RestAPIcredentials)
    credential._version = SimpleNamespace(checkmkVersion=version)
    credential.create_client = lambda: SimpleNamespace(post=request, put=request)
    model = SiteConnection()
    model.id = "client"
    model.extensions.configuration_connection.url_of_remote_site = "http://client.example.test:5000/client/check_mk/"
    getattr(SiteConnectionGateway(credential), operation)(model)
    config = calls[0]
    if version.startswith("2.4."):
        assert config == {"enable_replication": False}
    else:
        assert config["enable_replication"] is False
        assert config["user_sync"] == {"sync_with_ldap_connections": "disabled"}
        assert config["replicate_event_console"] is False
        assert config["replicate_extensions"] is False
        assert config["ignore_tls_errors"] is False
        assert config["is_trusted"] is False
        assert config["message_broker_port"] == 5672
        assert config["direct_login_to_web_gui_allowed"] is True
        assert config["disable_remote_configuration"] is False


def test_disabled_replication_cannot_inherit_user_sync_or_tls_suppression():
    connection = ConfigurationConnection(ignore_tls_errors=True)
    result = connection.to_dict(checkmk_version="2.5.0p11.community")
    assert result["ignore_tls_errors"] is False
    assert result["user_sync"] == {"sync_with_ldap_connections": "disabled"}


def test_explicit_replicating_configuration_remains_an_opt_in():
    connection = ConfigurationConnection(enable_replication=True, message_broker_port=6672, is_trusted=True)
    result = connection.to_dict(checkmk_version="2.5.0p11.community")
    assert result["enable_replication"] is True
    assert result["message_broker_port"] == 6672
    assert result["is_trusted"] is True
