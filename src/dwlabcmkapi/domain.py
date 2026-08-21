from dataclasses import dataclass


@dataclass(frozen=True)
class CmkSiteIdentity:
    site_name: str
    hostname: str
    domain: str

    def __post_init__(self):
        for field_name in ("site_name", "hostname", "domain"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if value == "":
                raise ValueError(f"{field_name} cannot be empty")

    @property
    def fqdn(self) -> str:
        return f"{self.hostname}.{self.domain}"

    @property
    def web_url(self) -> str:
        return f"https://{self.fqdn}/{self.site_name}/check_mk/"


@dataclass(frozen=True)
class CmkServer:
    identity: CmkSiteIdentity

    @property
    def site_name(self) -> str:
        return self.identity.site_name

    @property
    def hostname(self) -> str:
        return self.identity.hostname

    @property
    def domain(self) -> str:
        return self.identity.domain

    @property
    def fqdn(self) -> str:
        return self.identity.fqdn

    @property
    def web_url(self) -> str:
        return self.identity.web_url


@dataclass(frozen=True)
class CentralServer(CmkServer):
    ovpn_network: str
    ovpn_network_domain: str
    remote_instance_port: int = 8080

    def __post_init__(self):
        for field_name in ("ovpn_network", "ovpn_network_domain"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if value == "":
                raise ValueError(f"{field_name} cannot be empty")
        if not isinstance(self.remote_instance_port, int):
            raise TypeError("remote_instance_port must be an integer")
        if self.remote_instance_port <= 0:
            raise ValueError("remote_instance_port must be positive")

    def managed_host_name(self, client_site_name: str) -> str:
        if not isinstance(client_site_name, str):
            raise TypeError("client_site_name must be a string")
        if client_site_name == "":
            raise ValueError("client_site_name cannot be empty")
        return f"{client_site_name}.{self.ovpn_network}.{self.ovpn_network_domain}"

    def remote_site_url(self, client_site_name: str) -> str:
        managed_host = self.managed_host_name(client_site_name)
        return f"http://{managed_host}:{self.remote_instance_port}/{client_site_name}/check_mk/"

    def remote_status_url_prefix(self, client_site_name: str) -> str:
        managed_host = self.managed_host_name(client_site_name)
        return f"http://{managed_host}:{self.remote_instance_port}/{client_site_name}/"


@dataclass(frozen=True)
class ClientInstance(CmkServer):
    @property
    def instance_name(self) -> str:
        return self.site_name
