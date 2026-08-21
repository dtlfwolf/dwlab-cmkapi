import pytest

from dwlabcmkapi.domain import CentralServer, ClientInstance, CmkSiteIdentity
from dwlabcmkapi.services import (
    ClientCatalogService,
    ClientRetirementPlan,
    ClientRetirementService,
    SiteConnectionState,
    SiteInventoryService,
)


class FakeGateway:
    def __init__(self, host_exists=False, site_exists=False, status_host_enabled=False):
        self.host_exists = host_exists
        self.site_exists = site_exists
        self.status_host_enabled = status_host_enabled
        self.calls = []

    def get_host(self, host_name: str):
        self.calls.append(("get_host", host_name))
        return {"host_name": host_name} if self.host_exists else None

    def create_host(self, host_name: str, folder: str = "/", ip_address: str = ""):
        self.calls.append(("create_host", host_name, folder, ip_address))
        self.host_exists = True
        return {"host_name": host_name}

    def run_discovery(self, host_config) -> None:
        self.calls.append(("run_discovery", host_config["host_name"]))

    def activate_changes(self) -> str:
        self.calls.append(("activate_changes",))
        return "Done"

    def list_site_ids(self):
        self.calls.append(("list_site_ids",))
        return ["client01"] if self.site_exists else []

    def create_site_connection(self, site_id: str, remote_host: str, url_prefix: str, remote_site_url: str) -> None:
        self.calls.append(("create_site_connection", site_id, remote_host, url_prefix, remote_site_url))
        self.site_exists = True

    def get_site_connection(self, site_id: str):
        self.calls.append(("get_site_connection", site_id))
        if not self.site_exists:
            return None
        return SiteConnectionState(
            site_id=site_id,
            title=site_id,
            connection_socket_type="tcp",
            connection_host=f"{site_id}.vpn.example",
            status_host_enabled=self.status_host_enabled,
        )

    def enable_status_host(self, site_id: str, status_host: str, central_site_name: str) -> None:
        self.calls.append(("enable_status_host", site_id, status_host, central_site_name))
        self.status_host_enabled = True


def _central_server():
    return CentralServer(
        identity=CmkSiteIdentity(site_name="central", hostname="cmk", domain="example.org"),
        ovpn_network="vpn",
        ovpn_network_domain="dwlab",
    )


def _client_instance():
    return ClientInstance(
        identity=CmkSiteIdentity(site_name="client01", hostname="client01", domain="vpn.dwlab"),
    )


def test_central_server_builds_managed_host_information():
    central = _central_server()

    assert central.managed_host_name("client01") == "client01.vpn.dwlab"
    assert central.remote_status_url_prefix("client01") == "http://client01.vpn.dwlab:8080/client01/"
    assert central.remote_site_url("client01") == "http://client01.vpn.dwlab:8080/client01/check_mk/"


def test_catalog_service_creates_missing_host_and_site_connection():
    gateway = FakeGateway(host_exists=False, site_exists=False, status_host_enabled=False)
    service = ClientCatalogService(gateway)

    result = service.catalog_client(_central_server(), _client_instance())

    assert result.host_name == "client01.vpn.dwlab"
    assert result.host_created is True
    assert result.site_connection_created is True
    assert result.status_host_updated is True
    assert ("create_host", "client01.vpn.dwlab", "/", "") in gateway.calls
    assert (
        "create_site_connection",
        "client01",
        "client01.vpn.dwlab",
        "http://client01.vpn.dwlab:8080/client01/",
        "http://client01.vpn.dwlab:8080/client01/check_mk/",
    ) in gateway.calls
    assert ("enable_status_host", "client01", "client01.vpn.dwlab", "central") in gateway.calls


def test_catalog_service_reuses_existing_catalog_state():
    gateway = FakeGateway(host_exists=True, site_exists=True, status_host_enabled=True)
    service = ClientCatalogService(gateway)

    result = service.catalog_client(_central_server(), _client_instance())

    assert result.host_created is False
    assert result.site_connection_created is False
    assert result.status_host_updated is False
    assert all(call[0] != "create_host" for call in gateway.calls)
    assert all(call[0] != "create_site_connection" for call in gateway.calls)
    assert all(call[0] != "enable_status_host" for call in gateway.calls)


def test_catalog_service_requires_site_connection_after_creation_flow():
    class BrokenGateway(FakeGateway):
        def get_site_connection(self, site_id: str):
            self.calls.append(("get_site_connection", site_id))
            return None

    service = ClientCatalogService(BrokenGateway(host_exists=True, site_exists=True))

    with pytest.raises(RuntimeError, match="could not be loaded"):
        service.catalog_client(_central_server(), _client_instance())


def test_site_inventory_service_returns_sorted_site_ids():
    gateway = FakeGateway(host_exists=True, site_exists=True, status_host_enabled=True)
    gateway.list_site_ids = lambda: ["client02", "client01"]

    service = SiteInventoryService(gateway)

    assert service.list_site_ids() == ["client01", "client02"]


class FakeRetirementGateway:
    def __init__(self):
        self.revocations = []
        self.deleted_files = []
        self.deleted_directories = []
        self.deleted_prefixes = []

    def revoke_client(self, revoke_script: str, instance_name: str) -> bool:
        self.revocations.append((revoke_script, instance_name))
        return True

    def delete_file(self, path: str) -> bool:
        self.deleted_files.append(path)
        return not path.endswith(".missing")

    def delete_directory(self, path: str) -> bool:
        self.deleted_directories.append(path)
        return not path.endswith("missing")

    def delete_files_with_prefix(self, directory: str, prefix: str) -> list[str]:
        self.deleted_prefixes.append((directory, prefix))
        return [f"{directory}/{prefix}.deb", f"{directory}/{prefix}.changes"]


def test_client_retirement_service_executes_retirement_plan():
    gateway = FakeRetirementGateway()
    service = ClientRetirementService(gateway)
    plan = ClientRetirementPlan(
        instance_name="client01",
        revoke_script="/opt/dwlab/revoke.sh",
        revoke_enabled=True,
        files_to_delete=("/tmp/client01.conf", "/tmp/client01.missing"),
        directories_to_delete=("/tmp/client01", "/tmp/missing"),
        package_directory="/tmp/packages",
        package_prefix="dwlab-client01",
    )

    result = service.retire_client(plan)

    assert result.revoked is True
    assert result.deleted_files == ("/tmp/client01.conf",)
    assert result.deleted_directories == ("/tmp/client01",)
    assert result.deleted_package_files == (
        "/tmp/packages/dwlab-client01.deb",
        "/tmp/packages/dwlab-client01.changes",
    )
