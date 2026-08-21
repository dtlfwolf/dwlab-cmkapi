import json
import logging

from .api_client import CheckmkRestClient
from .api_credentials import RestAPIcredentials

logger = logging.getLogger(__name__)


class HostManagementGateway:
    def __init__(self, cmk_access: RestAPIcredentials):
        if not isinstance(cmk_access, RestAPIcredentials):
            raise TypeError("cmk_access must be an instance of RestAPIcredentials")
        self._cmk_access = cmk_access
        self._client = cmk_access.create_client()

    def get_host(self, host_name: str):
        from .api_hosts import HostConfig

        response = self._client.get("/objects/host_config/" + host_name)
        if response.status_code == 200:
            return HostConfig.from_dict(dataDict=response.json())
        if response.status_code == 404:
            return None
        raise RuntimeError(str(response.json()))

    def create_host(self, host_name: str, folder: str = "/", ip_address: str = ""):
        payload = {"host_name": host_name, "folder": folder, "attributes": {}}
        if ip_address != "":
            payload["attributes"]["ipaddress"] = ip_address

        response = self._client.post("/domain-types/host_config/collections/all", json_body=payload)
        if response.status_code == 200:
            return self.get_host(host_name)
        if response.status_code == 204:
            raise RuntimeWarning(response.status_code)
        raise RuntimeError(str(response.json()))

    def run_discovery(self, host_name: str, mode: str = "fix_all"):
        from .api_hosts import ServiceDiscovery

        payload = {"host_name": host_name, "mode": mode}
        response = self._client.post(
            "/domain-types/service_discovery_run/actions/start/invoke",
            json_body=payload,
        )
        if response.status_code == 200:
            return ServiceDiscovery.map_dataDict_to_serviceDiscovery(response.json())
        if response.status_code in {400, 403, 406, 409, 415}:
            logger.warning("run_discovery returned status %s: %s", response.status_code, response.json())
            return None
        if response.status_code == 204:
            raise RuntimeWarning(response.status_code)
        raise RuntimeError(str(response.json()))


class ActivationGateway:
    def __init__(self, cmk_access: RestAPIcredentials):
        if not isinstance(cmk_access, RestAPIcredentials):
            raise TypeError("cmk_access must be an instance of RestAPIcredentials")
        self._cmk_access = cmk_access
        self._client = cmk_access.create_client()

    def load_pending_changes(self):
        response = self._client.get("/domain-types/activation_run/collections/pending_changes")
        if response.status_code == 200:
            return response.headers["ETag"], response.json()
        if response.status_code in {403, 406}:
            raise RuntimeWarning(response.status_code)
        raise RuntimeError(str(response.json()))

    def activate_pending_changes(
        self,
        etag: str,
        redirect: bool = True,
        sites=None,
        force_foreign_changes: bool = False,
    ):
        if sites is None:
            sites = []

        payload = {
            "redirect": redirect,
            "sites": sites,
            "force_foreign_changes": force_foreign_changes,
        }
        response = self._client.post(
            "/domain-types/activation_run/actions/activate-changes/invoke",
            headers={"If-Match": etag},
            json_body=payload,
        )
        if response.status_code == 200:
            return "Started"
        if response.status_code == 204:
            return "Done"
        if response.status_code in {409, 412, 422}:
            return response.status_code
        raise RuntimeError(str(response.json()))


class SiteConnectionGateway:
    def __init__(self, cmk_access: RestAPIcredentials):
        if not isinstance(cmk_access, RestAPIcredentials):
            raise TypeError("cmk_access must be an instance of RestAPIcredentials")
        self._cmk_access = cmk_access
        self._client = cmk_access.create_client()

    def list_all(self):
        from .api_site_connections import Link, SiteAllConnections, SiteConnection

        response = self._client.get("/domain-types/site_connection/collections/all")
        if response.status_code == 204:
            raise RuntimeWarning(response.status_code)
        if response.status_code != 200:
            raise RuntimeError(str(response.json()))

        response_data = response.json()
        instance = object.__new__(SiteAllConnections)
        instance._links = [
            Link(
                domainType=link_data.get("domainType", ""),
                href=link_data.get("href", ""),
                method=link_data.get("method", ""),
                rel=link_data.get("rel", ""),
                type=link_data.get("type", ""),
            )
            for link_data in response_data.get("links", [])
        ]
        instance._id = response_data.get("id", "")
        instance._domainType = response_data.get("domainType", "")
        instance._title = response_data.get("title", "")
        instance._value = [
            SiteConnection.from_dict(dataDict=data_dict) for data_dict in response_data.get("value", [])
        ]
        instance._extensions = response_data.get("extensions", {})
        return instance

    def list_site_ids(self) -> list[str]:
        return self.list_all().getConnectedSiteIDs()

    def get_site_connection_model(self, site_id: str):
        return self.list_all().getConnectedSite(site_id)

    def create_site_connection(self, site_connection):
        payload = json.loads('{"site_config": ' + json.dumps(site_connection.extensions.to_dict()) + "}")
        response = self._client.post(
            "/domain-types/site_connection/collections/all",
            headers={"Content-Type": "application/json"},
            json_body=payload,
        )
        if response.status_code == 204:
            raise RuntimeWarning(response.status_code)
        if response.status_code != 200:
            raise RuntimeError(str(response.json()))

    def update_site_connection(self, site_connection):
        payload = json.loads('{"site_config": ' + json.dumps(site_connection.extensions.to_dict()) + "}")
        response = self._client.put(
            "/objects/site_connection/" + site_connection.id,
            headers={"Content-Type": "application/json"},
            json_body=payload,
        )
        if response.status_code == 204:
            raise RuntimeWarning(response.status_code)
        if response.status_code != 200:
            raise RuntimeError(str(response.json()))

    def delete_site_connection(self, site_id: str) -> None:
        response = self._client.delete("/objects/site_connection/" + site_id)
        if response.status_code not in {200, 204}:
            raise RuntimeError(str(response.json()))
