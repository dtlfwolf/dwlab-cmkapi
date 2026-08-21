from __future__ import annotations

import logging

from .api_credentials import RestAPIcredentials
from .api_site_connections import SiteConnection
from .operations import ActivationGateway, HostManagementGateway, SiteConnectionGateway
from .services import SiteConnectionState

logger = logging.getLogger(__name__)


class CheckmkGateway:
    def __init__(self, cmk_access: RestAPIcredentials):
        if not isinstance(cmk_access, RestAPIcredentials):
            raise TypeError("cmk_access must be an instance of RestAPIcredentials")
        self._cmk_access = cmk_access
        self._hosts = HostManagementGateway(cmk_access)
        self._activations = ActivationGateway(cmk_access)
        self._site_connections = SiteConnectionGateway(cmk_access)

    @property
    def cmk_access(self) -> RestAPIcredentials:
        return self._cmk_access

    def get_host(self, host_name: str):
        return self._hosts.get_host(host_name)

    def create_host(self, host_name: str, folder: str = "/", ip_address: str = ""):
        return self._hosts.create_host(host_name, folder=folder, ip_address=ip_address)

    def run_discovery(self, host_config, mode: str = "fix_all") -> None:
        self._hosts.run_discovery(host_config.id, mode=mode)
        return None

    def activate_changes(self) -> str:
        etag, _ = self._activations.load_pending_changes()
        return self._activations.activate_pending_changes(etag)

    def list_site_ids(self) -> list[str]:
        return self._site_connections.list_site_ids()

    def create_site_connection(
        self,
        site_id: str,
        remote_host: str,
        url_prefix: str,
        remote_site_url: str,
    ) -> None:
        suffix = f"{site_id}."
        if not remote_host.startswith(suffix):
            raise ValueError(
                "remote_host must start with the site_id prefix so the gateway can derive the OVPN naming"
            )

        ovpn_name = remote_host[len(suffix) :]
        if "." not in ovpn_name:
            raise ValueError("remote_host must include ovpn network and domain information")

        ovpn_network, ovpn_network_domain = ovpn_name.split(".", 1)
        site_connection = SiteConnection()
        site_connection.id = site_id
        site_connection.title = site_id
        site_connection.extensions.basic_settings.alias = site_id
        site_connection.extensions.basic_settings.site_id = site_id
        site_connection.extensions.status_connection.connection.host = remote_host
        site_connection.extensions.status_connection.url_prefix = url_prefix
        site_connection.extensions.configuration_connection.url_of_remote_site = remote_site_url
        self._site_connections.create_site_connection(site_connection)

    def get_site_connection(self, site_id: str):
        try:
            connection = self._site_connections.get_site_connection_model(site_id)
        except ResourceWarning:
            return None

        status_host = connection.extensions.status_connection.status_host
        return SiteConnectionState(
            site_id=site_id,
            title=connection.title,
            connection_socket_type=connection.extensions.status_connection.connection.socket_type,
            connection_host=connection.extensions.status_connection.connection.host,
            status_host_enabled=(status_host.status_host_set == "enabled"),
            status_host_host=status_host.host,
            status_host_site=status_host.site,
        )

    def delete_site_connection(self, site_id: str) -> None:
        self._site_connections.delete_site_connection(site_id)
        self.activate_changes()

    def enable_status_host(
        self,
        site_id: str,
        status_host: str,
        central_site_name: str,
    ) -> None:
        connection = self._site_connections.get_site_connection_model(site_id)
        if connection is None:
            raise RuntimeError(f"Site connection {site_id} could not be loaded")

        connection.extensions.status_connection.status_host.host = status_host
        connection.extensions.status_connection.status_host.status_host_set = "enabled"
        connection.extensions.status_connection.status_host.site = central_site_name
        self._site_connections.update_site_connection(connection)
