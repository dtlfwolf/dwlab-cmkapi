import inspect
import logging
import pprint

from .api_credentials import RestAPIcredentials
from .operations import HostManagementGateway

logger = logging.getLogger(__name__)


class Link:
    def __init__(self, domainType="link", href="", method="", rel="", type=""):
        self._domainType = domainType
        self._href = href
        self._method = method
        self._rel = rel
        self._type = type

    @property
    def domainType(self):
        return self._domainType

    @domainType.setter
    def domainType(self, value):
        self._domainType = value

    @property
    def href(self):
        return self._href

    @href.setter
    def href(self, value):
        self._href = value

    @property
    def method(self):
        return self._method

    @method.setter
    def method(self, value):
        self._method = value

    @property
    def rel(self):
        return self._rel

    @rel.setter
    def rel(self, value):
        self._rel = value

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self._type = value

    def to_dict(self):
        return {
            "domainType": self._domainType,
            "href": self._href,
            "method": self._method,
            "rel": self._rel,
            "type": self._type,
        }


class HostConfig:
    def __init__(
        self,
        domainType="host_config",
        extensions=None,
        id="",
        links=None,
        members=None,
        title="",
    ):
        self._domainType = domainType
        self._extensions = extensions if extensions is not None else HostExtensions()
        self._id = id
        self._links = links if links is not None else []
        self._members = members if members is not None else []
        self._title = title

    @property
    def domainType(self):
        return self._domainType

    @domainType.setter
    def domainType(self, value):
        self._domainType = value

    @property
    def extensions(self):
        return self._extensions

    @extensions.setter
    def extensions(self, value):
        self._hostExtensions = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def members(self):
        return self._members

    @members.setter
    def members(self, value):
        self._members = value

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    def to_dict(self):
        return {
            "domainType=": self._domainType,
            "extensions": self._extensions.to_dict(),
            "id": self._id,
            "links": [link.to_dict() for link in self._links],
            "members": self._members,
            "title": self._title,
        }

    @classmethod
    def from_dict(cls, dataDict=None):
        if dataDict is None:
            raise ValueError("dataDict is None")
        linkArray = []
        for linkDataDict in dataDict.get("links", []):
            link = Link(
                domainType=linkDataDict.get("domainType", ""),
                href=linkDataDict.get("href", ""),
                method=linkDataDict.get("method", ""),
                rel=linkDataDict.get("rel", ""),
                type=linkDataDict.get("type", ""),
            )
            linkArray.append(link)
        return cls(
            domainType=dataDict.get("domainType", ""),
            extensions=HostExtensions(
                folder=dataDict["extensions"].get("folder", {}),
                attributes=dataDict["extensions"].get("attributes", {}),
                effective_attributes=dataDict["extensions"].get("effective_attributes", {}),
                is_cluster=dataDict["extensions"].get("is_cluster", {}),
                is_offline=dataDict["extensions"].get("is_offline", {}),
                cluster_nodes=dataDict["extensions"].get("cluster_nodes", {}),
            ),
            id=dataDict.get("id", ""),
            links=linkArray,
            title=dataDict.get("title", ""),
            members=dataDict.get("members", {}),
        )

    @classmethod
    def ShowHost(cls, requestedHost="", cmkAccess=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        if not isinstance(cmkAccess, RestAPIcredentials):
            raise ValueError("cmkAccess are not of type RESTAPIcredentials")
        if requestedHost == "":
            raise ValueError("requestedHost is empty")
        if cmkAccess is None:
            raise ValueError("cmkAccess is empty")

        try:
            host_config = HostManagementGateway(cmkAccess).get_host(requestedHost)
        except Exception as e:
            logger.error("Error: " + str(e))
            raise

        logger.debug("Leaving function " + str(function_name))
        return host_config

    @classmethod
    def CreateHost(cls, folder="/", newHost="", ipAddress="", cmkAccess=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        if cmkAccess is None:
            raise ValueError("cmkCredentials are empty")
        if newHost == "":
            raise ValueError("newHost= is empty")

        host_config = HostManagementGateway(cmkAccess).create_host(
            newHost,
            folder=folder,
            ip_address=ipAddress,
        )

        logger.debug("Leaving function " + str(function_name))
        return host_config

    def executeDiscovery(self, mode="fix_all", cmkAccess=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        if mode not in ["new", "remove", "fix_all", "refresh", "only_host_labels", "tabula_rasa"]:
            raise ValueError("The given mode value is not supported")
        if cmkAccess is None:
            raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials:
            raise ValueError("cmkAccess is not of type RESTAPIcredentials")

        serviceDiscovery = HostManagementGateway(cmkAccess).run_discovery(self._id, mode=mode)

        logger.debug("Leaving function " + str(function_name))
        return serviceDiscovery


class HostExtensions:
    def __init__(
        self,
        folder="",
        attributes=None,
        effective_attributes=None,
        is_cluster=False,
        is_offline=False,
        cluster_nodes=None,
    ):
        self._folder = folder
        self._attributes = attributes if attributes is not None else {}
        self._effective_attributes = effective_attributes if effective_attributes is not None else {}
        self._is_cluster = is_cluster
        self._is_offline = is_offline
        self._cluster_nodes = cluster_nodes

    @property
    def folder(self):
        return self._folder

    @folder.setter
    def folder(self, value):
        self._folder = value

    @property
    def attributes(self):
        return self._attributes

    @attributes.setter
    def attributes(self, value):
        self._attributes = value

    @property
    def effective_attributes(self):
        return self._effective_attributes

    @effective_attributes.setter
    def effective_attributes(self, value):
        self._effective_attributes = value

    @property
    def is_cluster(self):
        return self._is_cluster

    @is_cluster.setter
    def is_cluster(self, value):
        self._is_cluster = value

    @property
    def is_offline(self):
        return self._is_offline

    @is_offline.setter
    def is_offline(self, value):
        self._is_offline = value

    @property
    def cluster_nodes(self):
        return self._cluster_nodes

    @cluster_nodes.setter
    def cluster_nodes(self, value):
        self._cluster_nodes = value

    def to_dict(self):
        return {
            "folder": self._folder,
            "attributes": self._attributes,
            "effective_attributes": self._effective_attributes,
            "is_cluster": self._is_cluster,
            "is_offline": self._is_offline,
            "cluster_nodes": self._cluster_nodes,
        }


class ServiceDiscovery:
    def __init__(
        self,
        domainType="service_discovery_config",
        extensions=None,
        id="",
        links=None,
        members=None,
        title="",
    ):
        self._domainType = domainType
        self._extensions = extensions if extensions is not None else ServiceDiscoveryExtensions()
        self._id = id
        self._links = links if links is not None else []
        self._members = members if members is not None else []
        self._title = title

    @property
    def domainType(self):
        return self._domainType

    @domainType.setter
    def domainType(self, value):
        self._domainType = value

    @property
    def extensions(self):
        return self._extensions

    @extensions.setter
    def extensions(self, value):
        self._hostExtensions = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def members(self):
        return self._members

    @members.setter
    def members(self, value):
        self._members = value

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    def to_dict(self):
        return {
            "domainType=": self._domainType,
            "extensions": self._extensions.to_dict(),
            "id": self._id,
            "links": [link.to_dict() for link in self._links],
            "members": self._members,
            "title": self._title,
        }

    def map_dataDict_to_serviceDiscovery(dataDict):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        linkArray = []
        for linkDataDict in dataDict.get("links", []):
            link = Link(
                domainType=linkDataDict.get("domainType", ""),
                href=linkDataDict.get("href", ""),
                method=linkDataDict.get("method", ""),
                rel=linkDataDict.get("rel", ""),
                type=linkDataDict.get("type", ""),
            )
            linkArray.append(link)

        serviceDiscovery = ServiceDiscovery(
            domainType=dataDict.get("domainType", ""),
            id=dataDict.get("id", ""),
            links=linkArray,
            title=dataDict.get("title", ""),
            members=dataDict.get("members", {}),
            extensions=ServiceDiscoveryExtensions(
                check_table=dataDict["extensions"].get("check_table", {}),
                host_labels=dataDict["extensions"].get("host_labels", {}),
                vanished_labels=dataDict["extensions"].get("vanished_labels", {}),
                changed_labels=dataDict["extensions"].get("changed_labels", {}),
            ),
        )

        logger.debug("Leaving function " + str(function_name))
        return serviceDiscovery


class ServiceDiscoveryExtensions:
    def __init__(self, check_table=dict(), host_labels=dict(), vanished_labels=dict(), changed_labels=dict()):
        self._check_table = check_table
        self._host_labels = host_labels
        self._vanished_labels = vanished_labels
        self._changed_labels = changed_labels

    @property
    def check_table(self):
        return self._check_table

    @check_table.setter
    def check_table(self, value):
        self._check_table = value

    @property
    def host_labels(self):
        return self._host_labels

    @host_labels.setter
    def host_labels(self, value):
        self._host_labels = value

    @property
    def vanished_labels(self):
        return self._vanished_labels

    @vanished_labels.setter
    def vanished_labels(self, value):
        self._vanished_labels = value

    @property
    def changed_labels(self):
        return self._changed_labels

    @changed_labels.setter
    def changed_labels(self, value):
        self._changed_labels = value

    def to_dict(self):
        return {
            "check_table": self._check_table,
            "host_labels": self._host_labels,
            "vanished_labels": self._vanished_labels,
            "changed_labels": self._changed_labels,
        }
