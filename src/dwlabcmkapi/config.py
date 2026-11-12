from dataclasses import dataclass
from pathlib import Path
from ipaddress import ip_address

from dwlabbasicpy import dwlabRuntimeEnvironment, dwlabSettings

from .api_credentials import RestAPIcredentials
from .domain import CentralServer, CmkSiteIdentity
from .settings_paths import resolve_central_server_settings_file


@dataclass(frozen=True)
class CentralServerConfig:
    env: object
    settings: object
    settings_file: Path
    server: CentralServer
    credentials: RestAPIcredentials


@dataclass(frozen=True)
class LocalApiConnectionPolicy:
    """Explicit local routing without changing provider or VPN identities."""

    address: str = "127.0.0.1"

    def __post_init__(self) -> None:
        if not ip_address(self.address).is_loopback:
            raise ValueError("cmkLocalApiAddress must be a literal loopback IP address")

    @classmethod
    def from_settings(cls, settings: dwlabSettings) -> "LocalApiConnectionPolicy":
        """Missing settings retain the reliable local-worker default."""
        return cls(str(settings.get_variable("cmkLocalApiAddress") or "127.0.0.1"))


def load_central_server_config(settings_file: str | Path | None = None, *,
                              local_api: bool = False) -> CentralServerConfig:
    env = dwlabRuntimeEnvironment()
    settings_path = resolve_central_server_settings_file(settings_file)

    settings = dwlabSettings.read_yaml(settings_path)

    central_hostname = settings.get_variable("centralHostname")
    central_domain = settings.get_variable("centralDomain")
    cmk_site_name = settings.get_variable("cmkSite")
    ovpn_network = settings.get_variable("ovpnNetwork")
    ovpn_network_domain = settings.get_variable("ovpnNetworkDomain")
    username = settings.get_variable("cmkadmin_username") or "cmkadmin"
    password = settings.get_variable("cmkadmin_password")

    server = CentralServer(
        identity=CmkSiteIdentity(
            site_name=cmk_site_name,
            hostname=central_hostname,
            domain=central_domain,
        ),
        ovpn_network=ovpn_network,
        ovpn_network_domain=ovpn_network_domain,
    )
    credentials = RestAPIcredentials(
        cmkHostname=central_hostname,
        cmkDomain=central_domain,
        cmkSiteName=cmk_site_name,
        username=username,
        password=password,
        connection_address=(LocalApiConnectionPolicy.from_settings(settings).address
                            if local_api else None),
    )

    return CentralServerConfig(
        env=env,
        settings=settings,
        settings_file=settings_path,
        server=server,
        credentials=credentials,
    )
