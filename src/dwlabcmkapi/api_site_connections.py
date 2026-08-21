import inspect
import json
import logging
import pprint

from . import api_credentials
from .api_credentials import RestAPIcredentials
from .operations import SiteConnectionGateway

logger = logging.getLogger(__name__)


class Link:
    def __init__(self, domainType="link", href="", method="", rel="", type=""):
        self._domainType = domainType
        self._href = href
        self._method = method
        self._rel = rel
        self._type = type

    def to_dict(self):
        return {
            "domainType": self._domainType,
            "href": self._href,
            "method": self._method,
            "rel": self._rel,
            "type": self._type,
        }


class Connection:
    def __init__(self, socket_type="tcp", host="", port=6557, encrypted=True, verify=False):
        self._socket_type = socket_type
        self._host = host
        self._port = port
        self._encrypted = encrypted
        self._verify = verify

    @property
    def socket_type(self):
        return self._socket_type

    @socket_type.setter
    def socket_type(self, value):
        self._socket_type = value

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        self._host = value

    def to_dict(self):
        return {
            "socket_type": self._socket_type,
            "host": self._host,
            "port": self._port,
            "encrypted": self._encrypted,
            "verify": self._verify,
        }


class Heartbeat:
    def __init__(self, interval=0, timeout=0):
        self._interval = interval
        self._timeout = timeout

    def to_dict(self):
        return {"interval": self._interval, "timeout": self._timeout}


class ProxyParams:
    def __init__(self, channels=0, heartbeat=None, channel_timeout=0, query_timeout=0, connect_retry=0, cache=False):
        self._channels = channels
        self._heartbeat = heartbeat if heartbeat is not None else Heartbeat()
        self._channel_timeout = channel_timeout
        self._query_timeout = query_timeout
        self._connect_retry = connect_retry
        self._cache = cache

    def to_dict(self):
        return {
            "channels": self._channels,
            "heartbeat": self._heartbeat.to_dict(),
            "channel_timeout": self._channel_timeout,
            "query_timeout": self._query_timeout,
            "connect_retry": self._connect_retry,
            "cache": self._cache,
        }


class ProxyTCP:
    def __init__(self, port=6560, only_from="", tls=False):
        self._port = port
        self._only_from = only_from
        self._tls = tls

    def to_dict(self):
        return {"port": self._port, "only_from": self._only_from, "tls": self._tls}


class Proxy:
    def __init__(self, use_livestatus_daemon="direct", global_settings=False, params=None, tcp=None):
        self._use_livestatus_daemon = use_livestatus_daemon
        self._global_settings = global_settings
        self._params = params if params is not None else ProxyParams()
        self._tcp = tcp if tcp is not None else ProxyTCP()

    def to_dict(self):
        data = {"use_livestatus_daemon": self._use_livestatus_daemon}
        if self._use_livestatus_daemon != "direct":
            data["global_settings"] = self._global_settings
            data["params"] = self._params.to_dict()
            data["tcp"] = self._tcp.to_dict()
        return data


class StatusHost:
    def __init__(self, status_host_set="disabled", site="", host=""):
        self._status_host_set = status_host_set
        self._site = site
        self._host = host

    @property
    def status_host_set(self):
        return self._status_host_set

    @status_host_set.setter
    def status_host_set(self, value):
        self._status_host_set = value

    @property
    def site(self):
        return self._site

    @site.setter
    def site(self, value):
        self._site = value

    @property
    def host(self):
        return self._host

    @host.setter
    def host(self, value):
        self._host = value

    def to_dict(self):
        data = {"status_host_set": self._status_host_set}
        if self._status_host_set != "disabled":
            data["host"] = self._host
            data["site"] = self._site
        return data


class StatusConnection:
    def __init__(self, connection=None, proxy=None, connect_timeout=5, persistent_connection=False, url_prefix="", status_host=None, disable_in_status_gui=False):
        self._connection = connection if connection is not None else Connection()
        self._proxy = proxy if proxy is not None else Proxy()
        self._connect_timeout = connect_timeout
        self._persistent_connection = persistent_connection
        self._url_prefix = url_prefix
        self._status_host = status_host if status_host is not None else StatusHost()
        self._disable_in_status_gui = disable_in_status_gui

    @property
    def connection(self):
        return self._connection

    @property
    def url_prefix(self):
        return self._url_prefix

    @url_prefix.setter
    def url_prefix(self, value):
        self._url_prefix = value

    @property
    def status_host(self):
        return self._status_host

    def to_dict(self):
        return {
            "connection": self._connection.to_dict(),
            "proxy": self._proxy.to_dict(),
            "connect_timeout": self._connect_timeout,
            "persistent_connection": self._persistent_connection,
            "url_prefix": self._url_prefix,
            "status_host": self._status_host.to_dict(),
            "disable_in_status_gui": self._disable_in_status_gui,
        }


class BasicSettings:
    def __init__(self, alias="", site_id=""):
        self._alias = alias
        self._site_id = site_id

    @property
    def alias(self):
        return self._alias

    @alias.setter
    def alias(self, value):
        self._alias = value

    @property
    def site_id(self):
        return self._site_id

    @site_id.setter
    def site_id(self, value):
        self._site_id = value

    def to_dict(self):
        return {"alias": self._alias, "site_id": self._site_id}


class UserSync:
    def __init__(self, sync_with_ldap_connections="all"):
        self._sync_with_ldap_connections = sync_with_ldap_connections

    def to_dict(self):
        return {"sync_with_ldap_connections": self._sync_with_ldap_connections}


class ConfigurationConnection:
    def __init__(self, enable_replication=False, url_of_remote_site="http://", disable_remote_configuration=False, ignore_tls_errors=False, direct_login_to_web_gui_allowed=True, user_sync=None, replicate_event_console=True, replicate_extensions=True):
        self._enable_replication = enable_replication
        self._url_of_remote_site = url_of_remote_site
        self._disable_remote_configuration = disable_remote_configuration
        self._ignore_tls_errors = ignore_tls_errors
        self._direct_login_to_web_gui_allowed = direct_login_to_web_gui_allowed
        self._user_sync = user_sync if isinstance(user_sync, UserSync) else UserSync()
        self._replicate_event_console = replicate_event_console
        self._replicate_extensions = replicate_extensions

    @property
    def url_of_remote_site(self):
        return self._url_of_remote_site

    @url_of_remote_site.setter
    def url_of_remote_site(self, value):
        self._url_of_remote_site = value

    def to_dict(self):
        if api_credentials.VERSION.checkmk_version <= "2.2":
            return self.to_dict_2_2()
        return self.to_dict_2_3()

    def to_dict_2_2(self):
        return {
            "enable_replication": self._enable_replication,
            "url_of_remote_site": self._url_of_remote_site,
            "disable_remote_configuration": self._disable_remote_configuration,
            "ignore_tls_errors": self._ignore_tls_errors,
            "direct_login_to_web_gui_allowed": self._direct_login_to_web_gui_allowed,
            "user_sync": self._user_sync.to_dict(),
            "replicate_event_console": self._replicate_event_console,
            "replicate_extensions": self._replicate_extensions,
        }

    def to_dict_2_3(self):
        if self._enable_replication:
            return self.to_dict_2_2()
        return {"enable_replication": self._enable_replication}


class Extensions:
    def __init__(self, basic_settings=None, status_connection=None, configuration_connection=None):
        self._basic_settings = basic_settings if basic_settings is not None else BasicSettings()
        self._status_connection = status_connection if status_connection is not None else StatusConnection()
        self._configuration_connection = configuration_connection if configuration_connection is not None else ConfigurationConnection()

    @property
    def basic_settings(self):
        return self._basic_settings

    @property
    def status_connection(self):
        return self._status_connection

    @property
    def configuration_connection(self):
        return self._configuration_connection

    def to_dict(self):
        return {
            "basic_settings": self._basic_settings.to_dict(),
            "status_connection": self._status_connection.to_dict(),
            "configuration_connection": self._configuration_connection.to_dict(),
        }


class SiteConnection:
    def __init__(self, links=None, domainType="site_connection", id="", title="", members=None, extensions=None):
        self._links = links if links is not None else []
        self._domainType = domainType
        self._id = id
        self._title = title
        self._members = members if members is not None else {}
        self._extensions = extensions if extensions is not None else Extensions()

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def extensions(self):
        return self._extensions

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "id": self._id,
            "domainType": self._domainType,
            "title": self._title,
            "extensions": self._extensions.to_dict(),
        }

    @classmethod
    def from_dict(cls, dataDict):
        linkArray = []
        for linkDataDict in dataDict.get("links", []):
            linkArray.append(
                Link(
                    domainType=linkDataDict.get("domainType", ""),
                    href=linkDataDict.get("href", ""),
                    method=linkDataDict.get("method", ""),
                    rel=linkDataDict.get("rel", ""),
                    type=linkDataDict.get("type", ""),
                )
            )
        extensions = Extensions(
            basic_settings=BasicSettings(
                alias=dataDict["extensions"].get("basic_settings", {}).get("alias", ""),
                site_id=dataDict["extensions"].get("basic_settings", {}).get("site_id", ""),
            ),
            status_connection=StatusConnection(
                connection=Connection(
                    socket_type=dataDict["extensions"].get("status_connection", {}).get("connection", {}).get("socket_type", "tcp"),
                    host=dataDict["extensions"].get("status_connection", {}).get("connection", {}).get("host", ""),
                    port=dataDict["extensions"].get("status_connection", {}).get("connection", {}).get("port", 0),
                    encrypted=dataDict["extensions"].get("status_connection", {}).get("connection", {}).get("encrypted", True),
                    verify=dataDict["extensions"].get("status_connection", {}).get("connection", {}).get("verify", False),
                ),
                proxy=Proxy(
                    use_livestatus_daemon=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("use_livestatus_daemon", "with_proxy"),
                    global_settings=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("global_settings", False),
                    params=ProxyParams(
                        channels=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("channels", 0),
                        heartbeat=Heartbeat(
                            dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("heartbeat", {}).get("interval", 0),
                            dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("heartbeat", {}).get("timeout", 0),
                        ),
                        channel_timeout=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("channel_timeout", 0),
                        query_timeout=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("query_timeout", 0),
                        connect_retry=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("connect_retry", 0),
                        cache=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("params", {}).get("cache", False),
                    ),
                    tcp=ProxyTCP(
                        port=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("tcp", {}).get("port", 0),
                        only_from=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("tcp", {}).get("only_from", []),
                        tls=dataDict["extensions"].get("status_connection", {}).get("proxy", {}).get("tcp", {}).get("tls", False),
                    ),
                ),
                connect_timeout=dataDict["extensions"].get("status_connection", {}).get("connect_timeout", 0),
                persistent_connection=dataDict["extensions"].get("status_connection", {}).get("persistent_connection", False),
                url_prefix=dataDict["extensions"].get("status_connection", {}).get("url_prefix", ""),
                status_host=StatusHost(
                    status_host_set=dataDict["extensions"].get("status_connection", {}).get("status_host", "").get("status_host_set", "disabled"),
                    host=dataDict["extensions"].get("status_connection", {}).get("status_host", "").get("host", ""),
                    site=dataDict["extensions"].get("status_connection", {}).get("status_host", "").get("site", ""),
                ),
                disable_in_status_gui=dataDict["extensions"].get("status_connection", {}).get("disable_in_status_gui", False),
            ),
            configuration_connection=ConfigurationConnection(
                enable_replication=dataDict["extensions"].get("configuration_connection", {}).get("enable_replication", True),
                url_of_remote_site=dataDict["extensions"].get("configuration_connection", {}).get("url_of_remote_site", ""),
                disable_remote_configuration=dataDict["extensions"].get("configuration_connection", {}).get("disable_remote_configuration", True),
                ignore_tls_errors=dataDict["extensions"].get("configuration_connection", {}).get("ignore_tls_errors", False),
                direct_login_to_web_gui_allowed=dataDict["extensions"].get("configuration_connection", {}).get("direct_login_to_web_gui_allowed", True),
                user_sync=UserSync(
                    sync_with_ldap_connections=dataDict["extensions"].get("configuration_connection", {}).get("user_sync", {}).get("sync_with_ldap_connections", {})
                ),
                replicate_event_console=dataDict["extensions"].get("configuration_connection", {}).get("replicate_event_console", True),
                replicate_extensions=dataDict["extensions"].get("configuration_connection", {}).get("replicate_extensions", True),
            ),
        )
        return cls(
            links=linkArray,
            domainType=dataDict.get("domainType", ""),
            id=dataDict.get("id", ""),
            title=dataDict.get("title", ""),
            members=dataDict.get("members", {}),
            extensions=extensions,
        )

    def createSiteConnection(self, cmkAccess=None, newSite="", ovpnNetwork="", ovpnNetworkDomain=""):
        def _create(version_site_name):
            linkArray = []
            for methodType in ["GET", "PUT", "DELETE"]:
                httpReference = "http://" + cmkAccess.cmkHostname + "/" + version_site_name + "/check_mk/api/1.0/objects/site_connection/" + newSite
                rel = "self" if methodType == "GET" else "urn:org.restfulobjects:rels/update" if methodType == "PUT" else "urn:org.restfulobjects:rels/delete"
                linkArray.append(Link(domainType="link", href=httpReference, method=methodType, rel=rel, type="application/json"))
            self.links = linkArray
            self.id = newSite
            self.title = newSite
            self.extensions.basic_settings.alias = newSite
            self.extensions.basic_settings.site_id = newSite
            self.extensions.status_connection.connection.host = newSite + "." + ovpnNetwork + "." + ovpnNetworkDomain
            self.extensions.status_connection.url_prefix = "http://" + newSite + "." + ovpnNetwork + "." + ovpnNetworkDomain + "/"
            self.extensions.configuration_connection.url_of_remote_site = "http://" + newSite + "." + ovpnNetwork + "." + ovpnNetworkDomain + "/check_mk/"
            SiteConnectionGateway(cmkAccess).create_site_connection(self)

        if not isinstance(cmkAccess, RestAPIcredentials):
            raise ValueError("cmkAccess is not of type RESTAPIcredentials")
        cmkVersion = str(api_credentials.VERSION.checkmk_version)
        if cmkVersion.startswith("2.2."):
            _create(cmkAccess.cmkSite)
        elif cmkVersion.startswith("2.3."):
            _create(cmkAccess.cmkSiteName)
        else:
            raise ValueError("cmkVersion is not supported")

    def updateSiteConnection(self, cmkAccess=None):
        if not isinstance(cmkAccess, RestAPIcredentials):
            raise ValueError("cmkAccess is not of type RestAPIcredentials")
        SiteConnectionGateway(cmkAccess).update_site_connection(self)


class SiteAllConnections:
    def __init__(self, cmkAccess=None):
        if cmkAccess is None:
            raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials:
            raise ValueError("cmkAccess are not of type RESTAPIcredentials")
        loaded = SiteConnectionGateway(cmkAccess).list_all()
        self._links = loaded._links
        self._id = loaded._id
        self._domainType = loaded._domainType
        self._title = loaded._title
        self._value = loaded._value
        self._extensions = loaded._extensions

    def getConnectedSiteIDs(self):
        return [site.id for site in self._value]

    def getConnectedSite(self, siteID):
        for site in self._value:
            if site.id == siteID:
                return site
        raise ResourceWarning("Site with ID " + str(siteID) + " not found")
