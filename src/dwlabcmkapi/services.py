from dataclasses import dataclass
from typing import Optional, Protocol

from .domain import CentralServer, ClientInstance


@dataclass(frozen=True)
class SiteConnectionState:
    site_id: str
    status_host_enabled: bool
    title: str = ""
    connection_socket_type: str = ""
    connection_host: str = ""
    status_host_host: str = ""
    status_host_site: str = ""


class CheckmkCatalogGateway(Protocol):
    def get_host(self, host_name: str):
        ...

    def create_host(self, host_name: str, folder: str = "/", ip_address: str = ""):
        ...

    def run_discovery(self, host_config) -> None:
        ...

    def activate_changes(self) -> str:
        ...

    def list_site_ids(self):
        ...

    def create_site_connection(
        self,
        site_id: str,
        remote_host: str,
        url_prefix: str,
        remote_site_url: str,
    ) -> None:
        ...

    def get_site_connection(self, site_id: str) -> Optional[SiteConnectionState]:
        ...

    def delete_site_connection(self, site_id: str) -> None:
        ...

    def enable_status_host(
        self,
        site_id: str,
        status_host: str,
        central_site_name: str,
    ) -> None:
        ...


@dataclass(frozen=True)
class ClientCatalogResult:
    host_name: str
    host_created: bool
    site_connection_created: bool
    status_host_updated: bool


class ClientCatalogService:
    def __init__(self, gateway: CheckmkCatalogGateway):
        self._gateway = gateway

    def catalog_client(
        self,
        central_server: CentralServer,
        client_instance: ClientInstance,
    ) -> ClientCatalogResult:
        host_name = central_server.managed_host_name(client_instance.instance_name)
        host_config = self._gateway.get_host(host_name)
        host_created = False

        if host_config is None:
            host_config = self._gateway.create_host(host_name=host_name, folder="/")
            self._gateway.activate_changes()
            self._gateway.run_discovery(host_config)
            self._gateway.activate_changes()
            host_created = True

        site_ids = set(self._gateway.list_site_ids())
        site_connection_created = False
        if client_instance.site_name not in site_ids:
            self._gateway.create_site_connection(
                site_id=client_instance.site_name,
                remote_host=host_name,
                url_prefix=central_server.remote_status_url_prefix(client_instance.instance_name),
                remote_site_url=central_server.remote_site_url(client_instance.instance_name),
            )
            site_connection_created = True

        connection_state = self._gateway.get_site_connection(client_instance.site_name)
        status_host_updated = False
        if connection_state is None:
            raise RuntimeError(f"Site connection {client_instance.site_name} could not be loaded")

        if not connection_state.status_host_enabled:
            self._gateway.enable_status_host(
                site_id=client_instance.site_name,
                status_host=host_name,
                central_site_name=central_server.site_name,
            )
            status_host_updated = True

        return ClientCatalogResult(
            host_name=host_name,
            host_created=host_created,
            site_connection_created=site_connection_created,
            status_host_updated=status_host_updated,
        )


class SiteInventoryService:
    def __init__(self, gateway: CheckmkCatalogGateway):
        self._gateway = gateway

    def list_site_ids(self) -> list[str]:
        return sorted(self._gateway.list_site_ids())

    def get_site_connection(self, site_id: str) -> Optional[SiteConnectionState]:
        return self._gateway.get_site_connection(site_id)


class ClientUncatalogService:
    def __init__(self, gateway: CheckmkCatalogGateway):
        self._gateway = gateway

    def uncatalog_client(self, client_instance: ClientInstance) -> bool:
        if self._gateway.get_site_connection(client_instance.site_name) is None:
            return False
        self._gateway.delete_site_connection(client_instance.site_name)
        return True


@dataclass(frozen=True)
class ClientRetirementPlan:
    instance_name: str
    revoke_script: str
    revoke_enabled: bool
    files_to_delete: tuple[str, ...]
    directories_to_delete: tuple[str, ...]
    package_directory: str
    package_prefix: str


@dataclass(frozen=True)
class ClientRetirementResult:
    revoked: bool
    deleted_files: tuple[str, ...]
    deleted_directories: tuple[str, ...]
    deleted_package_files: tuple[str, ...]


class ClientRetirementGateway(Protocol):
    def revoke_client(self, revoke_script: str, instance_name: str) -> bool:
        ...

    def delete_file(self, path: str) -> bool:
        ...

    def delete_directory(self, path: str) -> bool:
        ...

    def delete_files_with_prefix(self, directory: str, prefix: str) -> list[str]:
        ...


class ClientRetirementService:
    def __init__(self, gateway: ClientRetirementGateway):
        self._gateway = gateway

    def retire_client(self, plan: ClientRetirementPlan) -> ClientRetirementResult:
        revoked = False
        if plan.revoke_enabled:
            revoked = self._gateway.revoke_client(plan.revoke_script, plan.instance_name)

        deleted_files = tuple(
            path for path in plan.files_to_delete if self._gateway.delete_file(path)
        )
        deleted_directories = tuple(
            path for path in plan.directories_to_delete if self._gateway.delete_directory(path)
        )
        deleted_package_files = tuple(
            self._gateway.delete_files_with_prefix(plan.package_directory, plan.package_prefix)
        )

        return ClientRetirementResult(
            revoked=revoked,
            deleted_files=deleted_files,
            deleted_directories=deleted_directories,
            deleted_package_files=deleted_package_files,
        )
