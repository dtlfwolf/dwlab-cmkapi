import json
import logging
from typing import Optional

import requests
from dwlabbasicpy import dwlabSettings

from .api_client import CheckmkRestClient
from .credential_provider import SettingsCredentialResolver
from .settings_paths import resolve_central_server_settings_file

logger = logging.getLogger(__name__)

VERSION = None


def set_version(version):
    if not isinstance(version, Version):
        raise TypeError("version must be an instance of Version")

    global VERSION
    VERSION = version


class Version:
    def __init__(self, site, group, rest_api, versions, edition, demo,
                 api_path_version: Optional[str] = None):
        self.site = site
        self.group = group
        self.rest_api_revision = rest_api.get("revision", "")
        # Metadata revisions are not endpoint paths (Checkmk 2.5 reports "0").
        # Preserve direct-constructor compatibility; discovery pins its proven route.
        self._api_path_version = str(api_path_version if api_path_version is not None else self.rest_api_revision)
        self.checkmk_version = versions.get("checkmk", "")
        self.edition = edition
        self.demo = demo
        set_version(self)

    @classmethod
    def getVersion(cls, cmkAccess):
        if not isinstance(cmkAccess, RestAPIcredentials):
            raise TypeError("cmkAccess must be an instance of RestAPIcredentials")
        client = cmkAccess.create_client(apiVersion="1.0")
        try:
            resp = client.get("/version")
            if resp.status_code == 200:
                json_data = resp.json()
            else:
                raise RuntimeError(
                    f"Failed to retrieve version information. Status code: {resp.status_code}"
                )
        except requests.RequestException as e:
            raise RuntimeError(f"Error while accessing the API: {str(e)}")

        return cls(
            site=json_data.get("site", ""),
            group=json_data.get("group", ""),
            rest_api=json_data.get("rest_api", {}),
            versions=json_data.get("versions", {}),
            edition=json_data.get("edition", ""),
            demo=json_data.get("demo", False),
            api_path_version="1.0",
        )

    def to_dict(self):
        return {
            "site": self.site,
            "group": self.group,
            "rest_api": {"revision": self.rest_api_revision},
            "versions": {"checkmk": self.checkmk_version},
            "edition": self.edition,
            "demo": self.demo,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=4)

    @property
    def apiVersion(self):
        return self.rest_api_revision

    @apiVersion.setter
    def apiVersion(self, value):
        self.rest_api_revision = value
        self._api_path_version = str(value)

    @property
    def apiPathVersion(self) -> str:
        """The confirmed transport route, separate from the reported schema revision."""
        return self._api_path_version

    @property
    def checkmkVersion(self):
        return self.checkmk_version

    @checkmkVersion.setter
    def checkmkVersion(self, value):
        self.checkmk_version = value


class RestAPIcredentials:
    def __init__(
        self,
        cmkHostname="",
        cmkDomain="",
        cmkSiteName="",
        credentials=None,
        username=None,
        password=None,
        connection_address: Optional[str] = None,
    ):
        self._cmkHostname = cmkHostname
        self._cmkDomain = cmkDomain
        self._cmkSiteName = cmkSiteName
        self._credentials = credentials
        self._connection_address = connection_address
        self._username = None
        self._password = None
        if isinstance(username, str):
            self._username = username
        if isinstance(password, str):
            self._password = password
        if self._credentials is None:
            if self._username is None or self._password is None:
                raise ValueError("Username and password must be provided, if credentials are not define")
            self._credentials = "Bearer " + self._username + " " + self._password
        self._version = Version.getVersion(self)

    @property
    def connection_address(self) -> Optional[str]:
        """Optional literal connection IP; does not change the HTTPS identity."""
        return getattr(self, "_connection_address", None)

    @property
    def cmkHostname(self):
        return self._cmkHostname

    @cmkHostname.setter
    def cmkHostname(self, value):
        self._cmkHostname = value

    @property
    def cmkDomain(self):
        return self._cmkDomain

    @cmkDomain.setter
    def cmkDomain(self, value):
        self._cmkDomain = value

    @property
    def cmkSiteName(self):
        return self._cmkSiteName

    @cmkSiteName.setter
    def cmkSiteName(self, value):
        self._cmkSiteName = value

    @property
    def cmkSite(self):
        return self._cmkSiteName

    @property
    def credentials(self):
        return self._credentials

    @credentials.setter
    def credentials(self, value):
        self._credentials = value

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value):
        self._username = value

    @property
    def password(self):
        return "DW-Lab: Top secret -- not shown"

    @password.setter
    def password(self, value):
        self._password = value

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value):
        self._version = value
        set_version(self._version)

    def get_apiUrl(self, apiVersion=""):
        if apiVersion == "":
            apiVersion = getattr(self.version, "apiPathVersion", self.version.apiVersion)
        return (
            "https://"
            + str(self._cmkHostname)
            + "."
            + str(self._cmkDomain)
            + "/"
            + str(self._cmkSiteName)
            + "/check_mk/api/"
            + apiVersion
        )

    def create_client(self, apiVersion=""):
        return CheckmkRestClient.from_credentials(self, api_version=apiVersion)

    @classmethod
    def fromFile(cls, configFile=None):
        if configFile is None:
            configFile = resolve_central_server_settings_file()

        try:
            dwlab_IS = dwlabSettings.read_yaml(configFile)
        except Exception:
            logger.error("Cannot read installation setting.")
            raise RuntimeError("Cannot read installation setting.")

        cmkSite = dwlab_IS.get_variable("cmkSite")
        authentication = SettingsCredentialResolver().resolve(dwlab_IS, cmkSite)

        cmkHostname = dwlab_IS.get_variable("centralHostname")
        cmkDomain = dwlab_IS.get_variable("centralDomain")

        return cls(
            cmkHostname=cmkHostname,
            cmkDomain=cmkDomain,
            cmkSiteName=cmkSite,
            username=authentication.username,
            password=authentication.secret,
        )
