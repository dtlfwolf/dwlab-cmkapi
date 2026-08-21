import logging

from .api_credentials import RestAPIcredentials
from .domain import CentralServer, ClientInstance, CmkSiteIdentity
from .gateways import CheckmkGateway
from .services import ClientCatalogService

logger = logging.getLogger(__name__)


class CentralServerManager:
    def __init__(
        self,
        site_name: str,
        hostname: str,
        domain: str,
        ovpn_network: str,
        ovpn_network_domain: str,
        credentials: RestAPIcredentials,
    ):
        if not isinstance(credentials, RestAPIcredentials):
            raise TypeError("credentials must be an instance of RestAPIcredentials")
        for field_name, value in (
            ("site_name", site_name),
            ("hostname", hostname),
            ("domain", domain),
            ("ovpn_network", ovpn_network),
            ("ovpn_network_domain", ovpn_network_domain),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")

        self._credentials = credentials
        self._server = CentralServer(
            identity=CmkSiteIdentity(
                site_name=site_name,
                hostname=hostname,
                domain=domain,
            ),
            ovpn_network=ovpn_network,
            ovpn_network_domain=ovpn_network_domain,
        )

    @property
    def site_name(self):
        return self._server.site_name

    @property
    def hostname(self):
        return self._server.hostname

    @property
    def domain(self):
        return self._server.domain

    @property
    def version(self):
        return self._credentials.version

    @property
    def api_version(self):
        return self.version.apiVersion

    @property
    def checkmk_version(self):
        return self.version.checkmkVersion

    @property
    def ovpn_network(self):
        return self._server.ovpn_network

    @property
    def ovpn_network_domain(self):
        return self._server.ovpn_network_domain

    @property
    def credentials(self):
        return self._credentials

    def catalog_client(self, instance_name: str) -> None:
        if not isinstance(instance_name, str):
            raise TypeError("instance_name must be a string")
        if instance_name == "":
            raise ValueError("instance_name cannot be empty")

        client_instance = ClientInstance(
            identity=CmkSiteIdentity(
                site_name=instance_name,
                hostname=instance_name,
                domain=f"{self.ovpn_network}.{self.ovpn_network_domain}",
            )
        )
        result = ClientCatalogService(CheckmkGateway(self._credentials)).catalog_client(
            central_server=self._server,
            client_instance=client_instance,
        )
        logger.info(
            "Cataloged %s via service layer. host=%s host_created=%s "
            "site_connection_created=%s status_host_updated=%s",
            instance_name,
            result.host_name,
            result.host_created,
            result.site_connection_created,
            result.status_host_updated,
        )
