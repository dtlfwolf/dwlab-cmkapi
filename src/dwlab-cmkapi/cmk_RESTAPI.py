import requests
import pprint
import inspect
import json
from dwlab-basicpy import dwlabSettings
from dwlab-basicpy import dwlabRuntimeEnvironment
from pathlib import Path

import logging
logger=logging.getLogger(__name__)

VERSION=None
def set_version(version):
    if not isinstance(version,Version):
        raise TypeError("version must be an instance of Version")
    else:
        global VERSION
        VERSION=version

class Version:
    def __init__(self, site, group, rest_api, versions, edition, demo):
        self.site = site
        self.group = group
        self.rest_api_revision = rest_api.get("revision", "")
        self.checkmk_version = versions.get("checkmk", "")
        self.edition = edition
        self.demo = demo
        set_version(self)

    @classmethod
    def getVersion(cls, cmkAccess):
        if not isinstance(cmkAccess, RestAPIcredentials):
            raise TypeError("cmkAccess must be an instance of RestAPIcredentials")
        apiUrl=cmkAccess.get_apiUrl(apiVersion="1.0.0")
        requestUrl="/version"
        session = requests.session()
        session.headers['Authorization'] = cmkAccess.credentials
        try:
            resp = session.get(f"{apiUrl}{requestUrl}")
            if resp.status_code == 200:
                json_data = resp.json()
            else:
                raise RuntimeError(f"Failed to retrieve version information. Status code: {resp.status_code}")
        except requests.RequestException as e:
            raise RuntimeError(f"Error while accessing the API: {str(e)}")
        finally:
            session.close()


        return cls(
            site=json_data.get("site", ""),
            group=json_data.get("group", ""),
            rest_api=json_data.get("rest_api", {}),
            versions=json_data.get("versions", {}),
            edition=json_data.get("edition", ""),
            demo=json_data.get("demo", False)
        )

    def to_dict(self):
        return {
            "site": self.site,
            "group": self.group,
            "rest_api": {"revision": self.rest_api_revision},
            "versions": {"checkmk": self.checkmk_version},
            "edition": self.edition,
            "demo": self.demo
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=4)

    @property
    def apiVersion(self):
        return self.rest_api_revision
    @apiVersion.setter
    def apiVersion(self, value):
        self.rest_api_revision = value

    @property
    def checkmkVersion(self):
        return self.checkmk_version
    @checkmkVersion.setter
    def checkmkVersion(self, value):
        self.checkmk_version = value
    
class RestAPIcredentials:
    def __init__(self, 
                 cmkHostname="", 
                 cmkDomain="",
                 cmkSiteName="", 
                 credentials=None,
                 username=None,
                 password=None
                 ):
        self._cmkHostname=cmkHostname 
        self._cmkDomain=cmkDomain
        self._cmkSiteName=cmkSiteName
        self._credentials = credentials
        if isinstance(username,str):
            self._username=username
        if isinstance(password,str):
            self._password=password
        if self._credentials is None:
            if self._username is None or self._password is None:
                raise ValueError("Username and password must be provided, if credentials are not define")
            else:
                self._credentials="Bearer "+self._username+" "+self._password
        self._version=Version.getVersion(self)
    
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
        self._cmkSite = value

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
        return ("DW-Lab: Top secret -- not shown")
    @password.setter
    def password(self,value):
        self._password=value

    @property
    def version(self):
        return self._version
    @version.setter
    def version(self, value):
        self._version = value
        set_version(self._version)

    def get_apiUrl(self,apiVersion=""):
        if apiVersion=="":
            apiVersion=self.version.apiVersion
        apiUrl="https://"+str(self._cmkHostname)+"."+str(self._cmkDomain)+"/"+str(self._cmkSiteName)+"/check_mk/api/"+apiVersion
        return apiUrl

    
    @classmethod 
    def fromFile(cls,configFile=None):
        if configFile==None:
            ##
            ## Read the installation settings
            env=dwlabRuntimeEnvironment()
            configFile=Path.joinpath(env.dwlab_package_home,
                                        "etc",
                                        "dw-lab_InstallationSettings.yaml"
                                    )
            
        try:
            dwlab_IS=dwlabSettings.read_yaml(configFile)
        except:
            logger.error("Cannot read installation setting.")
            raise RuntimeError("Cannot read installation setting.")

        cmkSite=dwlab_IS.get_variable("cmkSite")

        username=dwlab_IS.get_variable("cmkadmin_username")
        password=dwlab_IS.get_variable("cmkadmin_password")
        if username=="":
            username="cmkadmin"
        credentials="Bearer "+username+" "+password
    
        cmkHostname=dwlab_IS.get_variable("centralHostname")
        cmkDomain=dwlab_IS.get_variable("centralDomain")
        
        return cls (
            cmkHostname=cmkHostname, 
            cmkDomain=cmkDomain,
            cmkSiteName=cmkSite, 
            credentials=credentials,
            username=username,
            password=password
        )
    
class Link:
    def __init__(self, 
                 domainType="link", 
                 href="", 
                 method="", 
                 rel="", 
                 type=""):
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
            "type": self._type
        }

class Hosts:
    def __init__(self, 
                 links=None, 
                 id="", 
                 disabledReason="", 
                 invalidReason="", 
                 x_ro_invalidReason="", 
                 memberType="", 
                 value=None, 
                 name="", 
                 title=""
        ):
        self._links = links if links is not None else []
        self._id = id
        self._disabledReason = disabledReason
        self._invalidReason = invalidReason
        self._x_ro_invalidReason = x_ro_invalidReason
        self._memberType = memberType
        self._value = value if value is not None else []
        self._name = name
        self._title = title

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def disabledReason(self):
        return self._disabledReason

    @disabledReason.setter
    def disabledReason(self, value):
        self._disabledReason = value

    @property
    def invalidReason(self):
        return self._invalidReason

    @invalidReason.setter
    def invalidReason(self, value):
        self._invalidReason = value

    @property
    def x_ro_invalidReason(self):
        return self._x_ro_invalidReason

    @x_ro_invalidReason.setter
    def x_ro_invalidReason(self, value):
        self._x_ro_invalidReason = value

    @property
    def memberType(self):
        return self._memberType

    @memberType.setter
    def memberType(self, value):
        self._memberType = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "id": self.id,
            "disabledReason": self.disabledReason,
            "invalidReason": self.invalidReason,
            "x_ro_invalidReason": self.x_ro_invalidReason,
            "memberType": self.memberType,
            "value": [value.to_dict() for value in self._value],
            "title": self.title
        }
    
class Move:
    def __init__(self, 
                 links=None, 
                 id="", 
                 disabledReason="", 
                 invalidReason="", 
                 x_ro_invalidReason="", 
                 memberType="", 
                 parameters=None, 
                 name="", 
                 title=""
        ):
        self._links = links if links is not None else []
        self._id = id
        self._disabledReason = disabledReason
        self._invalidReason = invalidReason
        self._x_ro_invalidReason = x_ro_invalidReason
        self._memberType = memberType
        self._parameters = parameters if parameters is not None else {}
        self._name = name
        self._title = title

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def disabledReason(self):
        return self._disabledReason

    @disabledReason.setter
    def disabledReason(self, value):
        self._disabledReason = value

    @property
    def invalidReason(self):
        return self._invalidReason

    @invalidReason.setter
    def invalidReason(self, value):
        self._invalidReason = value

    @property
    def x_ro_invalidReason(self):
        return self._x_ro_invalidReason

    @x_ro_invalidReason.setter
    def x_ro_invalidReason(self, value):
        self._x_ro_invalidReason = value

    @property
    def memberType(self):
        return self._memberType

    @memberType.setter
    def memberType(self, value):
        self._memberType = value

    @property
    def parameters(self):
        return self._parameters

    @parameters.setter
    def parameters(self, value):
        self._parameters = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "id": self.id,
            "disabledReason": self.disabledReason,
            "invalidReason": self.invalidReason,
            "x_ro_invalidReason": self.x_ro_invalidReason,
            "memberType": self.memberType,
            "parameters": self.parameters,
            "name": self.name,
            "title": self.title
        }

class FolderConfigMembers:
    def __init__(self, 
                 hosts=None, 
                 move=None
        ):
        self._hosts = hosts if hosts is not None else Hosts()
        self._move = move if move is not None else Move()

    @property
    def hosts(self):
        return self._hosts

    @hosts.setter
    def hosts(self, value):
        self._hosts = value

    @property
    def move(self):
        return self._move

    @move.setter
    def move(self, value):
        self._move = value

    def to_dict(self):
        return {
            "hosts": self._hosts.to_dict(),
            "move": self._move.to_dict()
        }

class FolderExtensions:
    def __init__(self, 
                 path="/", 
                 attributes=None
        ):
        self._path = path
        self._attributes = attributes if attributes is not None else {}

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value

    @property
    def attributes(self):
        return self._attributes

    @attributes.setter
    def attributes(self, value):    
        self._attributes = value

    def to_dict(self):
        return {
            "path": self._path,     
            "attributes": self._attributes
        }

class FolderConfig:
    def __init__(self, 
                 links=None, 
                 domainType="", 
                 id="", title="", 
                 members=None, 
                 extensions=None
        ):
        self._links = links if links is not None else []
        self._domainType = domainType
        self._id = id
        self._title = title
        self._members = members if members is not None else FolderConfigMembers()
        self._extensions = extensions if extensions is not None else FolderExtensions()

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def domainType(self):
        return self._domainType

    @domainType.setter
    def domainType(self, value):
        self._domainType = value

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
    def members(self):
        return self._members

    @members.setter
    def members(self, value):
        self._members = value

    @property
    def extensions(self):
        return self._extensions

    @extensions.setter
    def extensions(self, value):
        self._extensions = value
    
    def to_dict(self):
        return {
        "links": [link.to_dict() for link in self._links],
        "domainType": self._domainType,
        "id": self._id,
        "title": self._title,
        "members": self._members.to_dict(),
        "extensions": self._extensions.to_dict()
    }

class Members:
    def __init__(self, 
                 folder_config=None
        ):
        self._folder_config = folder_config if folder_config is not None else FolderConfig()

    @property
    def folder_config(self):
        return self._folder_config

    @folder_config.setter
    def folder_config(self, value):
        self._folder_config = value
    
    def to_dict(self):
        return {
            "folder_config": self._folder_config.to_dict()
        }

class HostConfig:
    def __init__(self, 
                 domainType="host_config", 
                 extensions=None, 
                 id="", 
                 links=None, 
                 members=None, 
                 title=""
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
        resultDict=dict()
        resultDict["domainType="] = self._domainType
        resultDict["extensions"] = self._extensions.to_dict()
        resultDict["id"] =self._id
        resultDict["links"] = [link.to_dict() for link in self._links]
        resultDict["members"] = self._members
        resultDict["title"] = self._title

        return resultDict

    @classmethod
    def from_dict(cls,dataDict=None):
        
        if dataDict is None:
            raise ValueError("dataDict is None")
        linkArray=[]
        for linkDataDict in dataDict.get('links', []):
            link=Link(domainType=linkDataDict.get('domainType',''),
                      href=linkDataDict.get('href',''),
                      method=linkDataDict.get('method',''),
                      rel=linkDataDict.get('rel',''),
                      type=linkDataDict.get('type','')
            )
            linkArray.append(link)
        hostconfig=cls(
            domainType=dataDict.get('domainType', ""),
            extensions=HostExtensions(
                folder=dataDict['extensions'].get('folder', {}),
                attributes=dataDict['extensions'].get('attributes', {}),
                effective_attributes=dataDict['extensions'].get('effective_attributes', {}),
                is_cluster=dataDict['extensions'].get('is_cluster', {}),
                is_offline=dataDict['extensions'].get('is_offline', {}),
                cluster_nodes=dataDict['extensions'].get('cluster_nodes', {})
            ),
            id=dataDict.get('id', ""),
            links=linkArray,
            title=dataDict.get('title', ""),
            members=dataDict.get('members', {})
        )
        return hostconfig

    @classmethod
    def ShowHost(cls, requestedHost="", cmkAccess=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))
        
        if not isinstance(cmkAccess,RestAPIcredentials): raise ValueError("cmkAccess are not of type RESTAPIcredentials")

        if requestedHost == "": raise ValueError("requestedHost is empty")
        if cmkAccess == None: raise ValueError("cmkAccess is empty")
        
        host_config=None
        apiUrl=cmkAccess.get_apiUrl()
        requestUrl="/objects/host_config/"+requestedHost

        session = requests.session()
        session.headers['Authorization'] = f"{cmkAccess.credentials}"
        session.headers['Accept'] = 'application/json'

        resp = session.get(apiUrl+requestUrl)
        if resp.status_code == 200:
            response_data=resp.json()
            logger.debug("API request status_code : "+str(resp.status_code))
            logger.debug(str(response_data))
            try:
                host_config=cls.from_dict(dataDict=response_data)
            except Exception as e:
                logger.error("Error: "+str(e))
                raise RuntimeError(print(resp.json()))

        elif resp.status_code == 404:
            logger.warning("API request status_code : "+str(resp.status_code))
            logger.warning("Host "+str(requestedHost)+" not found")
            host_config=None
        else:
            logger.error(pprint.pformat(resp.json()))
            raise RuntimeError(pprint.pformat(resp.json()))    


        logger.debug("Leaving function "+str(function_name))
        
        return host_config

    @ classmethod
    def CreateHost(
            cls,
            folder="/",
            newHost="",
            ipAddress="",
            cmkAccess=None
        ):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))
        
        if cmkAccess == None: raise ValueError("cmkCredentials are empty")

        if newHost == "": raise ValueError("newHost= is empty")
        
        host_config=None
        
        
        apiUrl=cmkAccess.get_apiUrl()
        requestUrl="/domain-types/host_config/collections/all"

        session = requests.session()
        session.headers['Authorization'] = cmkAccess.credentials
        session.headers['Accept'] = 'application/json'

        payLoad=dict()
        payLoad["host_name"] = newHost
        payLoad["folder"] = folder
        payLoad["attributes"] = dict()
        if ipAddress != "":
            payLoad["attributes"]["ipaddress"] = ipAddress

        resp = session.post(apiUrl+requestUrl,json=payLoad)
        if resp.status_code == 200:
            try:
                host_config=cls.ShowHost(requestedHost=newHost,cmkAccess=cmkAccess)
            except Exception as e:
                logger.debug("Error: "+str(e))
                raise(e)
                
        elif resp.status_code == 204:
            logger.warning("API request status_code : "+str(resp.status_code))
            raise RuntimeWarning(resp.status_code)
        else:
            raise RuntimeError(print(resp.json()))

        logger.debug("Leaving function "+str(function_name))
        return host_config


    
    def executeDiscovery(self,mode="fix_all", cmkAccess=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))

        if mode not in ["new", "remove", "fix_all", "refresh", "only_host_labels", "tabula_rasa"]: raise ValueError("The given mode value is not supported")
        if cmkAccess == None: raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials: raise ValueError("cmkAccess is not of type RESTAPIcredentials")



        apiUrl=cmkAccess.get_apiUrl()
        requestUrl="/domain-types/service_discovery_run/actions/start/invoke"

        session = requests.session()
        session.headers['Authorization'] = cmkAccess.credentials
        session.headers['Accept'] = 'application/json'

        payLoad=dict()
        payLoad["host_name"] = self._id
        payLoad["mode"] = mode

        resp = session.post(apiUrl+requestUrl,json=payLoad)
        if resp.status_code == 200:
            responseData=resp.json()
            serviceDiscovery=ServiceDiscovery.map_dataDict_to_serviceDiscovery(responseData)
            logger.info(function_name+" responded:")
            logger.info("Service discovery name : "+serviceDiscovery.id)
            logger.info("Title                  : "+serviceDiscovery.title)
            logger.info("API status code        : "+str(resp.status_code))
            logger.info("Discovery successfully executed with parameter : "+str(mode))
        elif resp.status_code == 204:
            logger.warning("API request status_code : "+str(resp.status_code))
            raise RuntimeWarning(resp.status_code)
        elif resp.status_code == 400:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("Bad request     : Parameter or validation error.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            serviceDiscovery=None
        elif resp.status_code == 403:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("Forbidden       : Configuration via setup is disabled.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            serviceDiscovery=None
        elif resp.status_code == 406:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("Not acceptable  : The requests headers can not be satisfied.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            serviceDiscovery=None
        elif resp.status_code == 409:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("Conflict        : A service discovery background job is currently running.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            serviceDiscovery=None
        elif resp.status_code == 415:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("Unsup. MediaType: The supported content-type is not supported.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            serviceDiscovery=None
        else:
            raise RuntimeError(print(resp.json()))



        logger.debug("Leaving function "+str(function_name))
        
        return serviceDiscovery

class HostExtensions:
    def __init__(self, 
                 folder="", 
                 attributes=None, 
                 effective_attributes=None, 
                 is_cluster=False, 
                 is_offline=False, 
                 cluster_nodes=None
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
        resultDict=dict()
        resultDict["folder"] = self._folder
        resultDict["attributes"] = self._attributes
        resultDict["effective_attributes"] = self._effective_attributes
        resultDict["is_cluster"] = self._is_cluster
        resultDict["is_offline"] = self._is_offline
        resultDict["cluster_nodes"] = self._cluster_nodes

        return resultDict

class ServiceDiscovery:
    def __init__(self, 
                 domainType="service_discovery_config", 
                 extensions=None, 
                 id="", 
                 links=None, 
                 members=None, 
                 title=""):
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
        resultDict=dict()
        resultDict["domainType="] = self._domainType
        resultDict["extensions"] = self._extensions.to_dict()
        resultDict["id"] =self._id
        resultDict["links"] = [link.to_dict() for link in self._links]
        resultDict["members"] = self._members
        resultDict["title"] = self._title

        return resultDict

    def map_dataDict_to_serviceDiscovery(dataDict):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))
        
        linkArray=[]
        for linkDataDict in dataDict.get('links', []):
            link=Link(domainType=linkDataDict.get('domainType',''),
                      href=linkDataDict.get('href',''),
                      method=linkDataDict.get('method',''),
                      rel=linkDataDict.get('rel',''),
                      type=linkDataDict.get('type',''))
            linkArray.append(link)

        serviceDiscovery=ServiceDiscovery(
            domainType=dataDict.get('domainType', ""),
            id=dataDict.get('id', ""),
            links=linkArray,
            title=dataDict.get('title', ""),
            members=dataDict.get('members', {}),
            extensions=ServiceDiscoveryExtensions(
                check_table=dataDict['extensions'].get('check_table', {}),
                host_labels=dataDict['extensions'].get('host_labels', {}),
                vanished_labels=dataDict['extensions'].get('vanished_labels', {}),
                changed_labels=dataDict['extensions'].get('changed_labels', {})
            )
        )

        logger.debug("Leaving function "+str(function_name))
        return serviceDiscovery

class ServiceDiscoveryExtensions:
    def __init__(self, 
                 check_table=dict(), 
                 host_labels=dict(), 
                 vanished_labels=dict(), 
                 changed_labels=dict()):
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
            "changed_labels": self._changed_labels
        }

class Connection:
    def __init__(self, 
                 socket_type="tcp", 
                 host="", 
                 port=6557, 
                 encrypted=True, 
                 verify=False):
         
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

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        self._port = value

    @property
    def encrypted(self):
        return self._encrypted

    @encrypted.setter
    def encrypted(self, value):
        self._encrypted = value

    @property
    def verify(self):
        return self._verify

    @verify.setter
    def verify(self, value):
        self._verify = value
    
    def to_dict(self):
        return {
            "socket_type": self._socket_type,
            "host": self._host,
            "port": self._port,
            "encrypted": self._encrypted,
            "verify": self._verify
        }

class ProxyParams:
    def __init__(self, 
                 channels=0, 
                 heartbeat=None, 
                 channel_timeout=0, 
                 query_timeout=0, 
                 connect_retry=0, 
                 cache=False):
         
        self._channels = channels
        self._heartbeat = heartbeat if heartbeat is not None else Heartbeat()
        self._channel_timeout = channel_timeout
        self._query_timeout = query_timeout
        self._connect_retry = connect_retry
        self._cache = cache

    @property
    def channels(self):
        return self._channels

    @channels.setter
    def channels(self, value):
        self._channels = value

    @property
    def heartbeat(self):
        return self._heartbeat

    @heartbeat.setter
    def heartbeat(self, value):
        self._heartbeat = value

    @property
    def channel_timeout(self):
        return self._channel_timeout

    @channel_timeout.setter
    def channel_timeout(self, value):
        self._channel_timeout = value

    @property
    def query_timeout(self):
        return self._query_timeout

    @query_timeout.setter
    def query_timeout(self, value):
        self._query_timeout = value

    @property
    def connect_retry(self):
        return self._connect_retry

    @connect_retry.setter
    def connect_retry(self, value):
        self._connect_retry = value

    @property
    def cache(self):
        return self._cache

    @cache.setter
    def cache(self, value):
        self._cache = value
    
    def to_dict(self):
        return {
            "channels": self._channels,
            "heartbeat": self._heartbeat.to_dict(),
            "channel_timeout": self._channel_timeout,
            "query_timeout": self._query_timeout,
            "connect_retry": self._connect_retry,
            "cache": self._cache
        }

class ProxyTCP:
    def __init__(self, 
                 port=6560, 
                 only_from="", 
                 tls=False):
         
        self._port = port
        self._only_from = only_from
        self._tls = tls

    @property
    def port(self):
        return self._port

    @port.setter
    def port(self, value):
        self._port = value

    @property
    def only_from(self):
        return self._only_from

    @only_from.setter
    def only_from(self, value):
        self._only_from = value

    @property
    def tls(self):
        return self._tls

    @tls.setter
    def tls(self, value):
        self._tls = value
    
    def to_dict(self):
        return {
            "port": self._port,
            "only_from": self._only_from,
            "tls": self._tls
        }

class Proxy:
    def __init__(self, 
                 use_livestatus_daemon="direct", 
                 global_settings=False, 
                 params=None, 
                 tcp=None):
         
        self._use_livestatus_daemon = use_livestatus_daemon
        self._global_settings = global_settings
        self._params = params if params is not None else ProxyParams()
        self._tcp = tcp if tcp is not None else ProxyTCP()

    @property
    def use_livestatus_daemon(self):
        return self._use_livestatus_daemon

    @use_livestatus_daemon.setter
    def use_livestatus_daemon(self, value):
        self._use_livestatus_daemon = value

    @property
    def global_settings(self):
        return self._global_settings

    @global_settings.setter
    def global_settings(self, value):
        self._global_settings = value

    @property
    def params(self):
        return self._params

    @params.setter
    def params(self, value):
        self._params = value

    @property
    def tcp(self):
        return self._tcp

    @tcp.setter
    def tcp(self, value):
        self._tcp = value
    
    def to_dict(self):
        returnDict={}
        returnDict["use_livestatus_daemon"] = self._use_livestatus_daemon
        if self._use_livestatus_daemon!="direct":
            returnDict["global_settings"] = self._global_settings
            returnDict["params"] = self._params.to_dict()
            returnDict["tcp"] = self._tcp.to_dict()
        
        return returnDict

class StatusConnection:
    def __init__(self, 
                 connection=None, 
                 proxy=None, 
                 connect_timeout=5, 
                 persistent_connection=False, 
                 url_prefix="", 
                 status_host=None, 
                 disable_in_status_gui=False):
         
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

    @connection.setter
    def connection(self, value):
        self._connection = value

    @property
    def proxy(self):
        return self._proxy

    @proxy.setter
    def proxy(self, value):
        self._proxy = value

    @property
    def connect_timeout(self):
        return self._connect_timeout

    @connect_timeout.setter
    def connect_timeout(self, value):
        self._connect_timeout = value

    @property
    def persistent_connection(self):
        return self._persistent_connection

    @persistent_connection.setter
    def persistent_connection(self, value):
        self._persistent_connection = value

    @property
    def url_prefix(self):
        return self._url_prefix

    @url_prefix.setter
    def url_prefix(self, value):
        self._url_prefix = value

    @property
    def status_host(self):
        return self._status_host

    @status_host.setter
    def status_host(self, value):
        self._status_host = value

    @property
    def disable_in_status_gui(self):
        return self._disable_in_status_gui

    @disable_in_status_gui.setter
    def disable_in_status_gui(self, value):
        self._disable_in_status_gui = value
    
    def toJson(self):
        return json.dumps(self.__dict__)

    def to_dict(self):
        resultDict={}
        resultDict["connection"] = self._connection.to_dict()
        resultDict["proxy"] = self._proxy.to_dict()
        resultDict["connect_timeout"] = self._connect_timeout
        resultDict["persistent_connection"] = self._persistent_connection
        resultDict["url_prefix"] = self._url_prefix
        resultDict["status_host"] = self._status_host.to_dict()
        resultDict["disable_in_status_gui"] = self._disable_in_status_gui

        return resultDict

class BasicSettings:
    def __init__(self, 
                 alias="", 
                 site_id=""
        ):
         
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
        return {
            "alias": self._alias,
            "site_id": self._site_id
        }

class StatusHost:
    def __init__(self, 
                 status_host_set="disabled", 
                 site="", 
                 host=""
        ):
         
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
        returnDict={}
        returnDict["status_host_set"] = self._status_host_set
        if self._status_host_set!="disabled":
            returnDict["host"] = self._host
            returnDict["site"] = self._site
        
        return returnDict

class Heartbeat:
    def __init__(self, 
                 interval=0, 
                 timeout=0
        ):
         
        self._interval = interval
        self._timeout = timeout

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, value):
        self._timeout = value

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value

    def to_dict(self):
        return {
            "interval": self._interval,
            "timeout": self._timeout
        }

class UserSync:
    def __init__(self, 
                 sync_with_ldap_connections="all"
        ):
         
        self._sync_with_ldap_connections = sync_with_ldap_connections

    @property
    def sync_with_ldap_connections(self):
        return self._sync_with_ldap_connections

    @sync_with_ldap_connections.setter
    def sync_with_ldap_connections(self, value):
        self._timeout = value

    def to_dict(self):
        return {
            "sync_with_ldap_connections": self._sync_with_ldap_connections
        }

class ConfigurationConnection:
    def __init__(
            self, enable_replication=False, 
            url_of_remote_site="http://", 
            disable_remote_configuration=False, 
            ignore_tls_errors=False, 
            direct_login_to_web_gui_allowed=True, 
            user_sync=None, 
            replicate_event_console=True, 
            replicate_extensions=True
        ):
         
        if not isinstance(user_sync,UserSync):
            user_sync=UserSync()
        self._enable_replication = enable_replication
        if self._enable_replication:
            self._url_of_remote_site = url_of_remote_site
            self._disable_remote_configuration = disable_remote_configuration
            self._ignore_tls_errors = ignore_tls_errors
            self._direct_login_to_web_gui_allowed = direct_login_to_web_gui_allowed
            self._user_sync = user_sync
            self._replicate_event_console = replicate_event_console
            self._replicate_extensions = replicate_extensions
        
    @property
    def enable_replication(self):
        return self._enable_replication

    @enable_replication.setter
    def enable_replication(self, value):
        self._enable_replication = value

    @property
    def url_of_remote_site(self):
        return self._url_of_remote_site

    @url_of_remote_site.setter
    def url_of_remote_site(self, value):
        self._url_of_remote_site = value

    @property
    def disable_remote_configuration(self):
        return self._disable_remote_configuration

    @disable_remote_configuration.setter
    def disable_remote_configuration(self, value):
        self._disable_remote_configuration = value

    @property
    def ignore_tls_errors(self):
        return self._ignore_tls_errors

    @ignore_tls_errors.setter
    def ignore_tls_errors(self, value):
        self._ignore_tls_errors = value

    @property
    def direct_login_to_web_gui_allowed(self):
        return self._direct_login_to_web_gui_allowed

    @direct_login_to_web_gui_allowed.setter
    def direct_login_to_web_gui_allowed(self, value):
        self._direct_login_to_web_gui_allowed = value

    @property
    def user_sync(self):
        return self._user_sync

    @user_sync.setter
    def user_sync(self, value):
        self._user_sync = value

    @property
    def replicate_event_console(self):
        return self._replicate_event_console

    @replicate_event_console.setter
    def replicate_event_console(self, value):
        self._replicate_event_console = value

    @property
    def replicate_extensions(self):
        return self._replicate_extensions

    @replicate_extensions.setter
    def replicate_extensions(self, value):
        self._replicate_extensions = value
    
    def to_dict(self):
        if VERSION.checkmk_version<="2.2":return self.to_dict_2_2()
        if VERSION.checkmk_version>="2.3":return self.to_dict_2_3()

    def to_dict_2_2(self):
        localDict={
            "enable_replication": self._enable_replication,
            "url_of_remote_site": self._url_of_remote_site,
            "disable_remote_configuration": self._disable_remote_configuration,
            "ignore_tls_errors": self._ignore_tls_errors,
            "direct_login_to_web_gui_allowed": self._direct_login_to_web_gui_allowed,
            "user_sync": self._user_sync.to_dict(),
            "replicate_event_console": self._replicate_event_console,
            "replicate_extensions": self._replicate_extensions
        }
        return localDict

    def to_dict_2_3(self):
        if self._enable_replication:
            localDict={
                "enable_replication": self._enable_replication,
                "url_of_remote_site": self._url_of_remote_site,
                "disable_remote_configuration": self._disable_remote_configuration,
                "ignore_tls_errors": self._ignore_tls_errors,
                "direct_login_to_web_gui_allowed": self._direct_login_to_web_gui_allowed,
                "user_sync": self._user_sync.to_dict(),
                "replicate_event_console": self._replicate_event_console,
                "replicate_extensions": self._replicate_extensions
            }
        else:
            localDict={
                "enable_replication": self._enable_replication
            }   
        return localDict

class Extensions:
    def __init__(self, 
                 basic_settings=None, 
                 status_connection=None, 
                 configuration_connection=None
        ):
         
        if basic_settings is None:
            basic_settings = BasicSettings()
        if status_connection is None:
            status_connection = StatusConnection()
        if configuration_connection is None:
            configuration_connection = ConfigurationConnection()
        self._basic_settings = basic_settings
        self._status_connection = status_connection
        self._configuration_connection = configuration_connection
        
    @property
    def basic_settings(self):
        return self._basic_settings

    @basic_settings.setter
    def basic_settings(self, value):
        self._basic_settings = value

    @property
    def status_connection(self):
        return self._status_connection

    @status_connection.setter
    def status_connection(self, value):
        self._status_connection = value

    @property
    def configuration_connection(self):
        return self._configuration_connection

    @configuration_connection.setter
    def configuration_connection(self, value):
        self._configuration_connection = value
    
    def to_dict(self):
        return {
            "basic_settings": self._basic_settings.to_dict(),
            "status_connection": self._status_connection.to_dict(),
            "configuration_connection": self._configuration_connection.to_dict()
        }    

class SiteConnection:
    def __init__(self, 
                 links=[], 
                 domainType="site_connection", 
                 id="", title="", 
                 members=None, 
                 extensions=None
        ):
        self._links = links
        self._domainType = domainType
        self._id = id
        self._title = title
        self._members = members if members is not None else {}
        self._extensions = extensions if extensions is not None else Extensions()

    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def domainType(self):
        return self._domainType

    @domainType.setter
    def domainType(self, value):
        self._domainType = value

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
    def members(self):
        return self._members

    @members.setter
    def members(self, value):
        self._members = value

    @property
    def extensions(self):
        return self._extensions

    @extensions.setter
    def extensions(self, value):
        self._extensions = value
    
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
        for linkDataDict in dataDict.get('links', []):
            link = Link(domainType=linkDataDict.get('domainType', ''),
                      href=linkDataDict.get('href', ''),
                      method=linkDataDict.get('method', ''),
                      rel=linkDataDict.get('rel', ''),
                      type=linkDataDict.get('type', '')
            )
            linkArray.append(link)

        links = linkArray
        domainType = dataDict.get('domainType', "")
        id = dataDict.get('id', "")
        title = dataDict.get('title', "")
        members = dataDict.get('members', {})
        extensions = Extensions(
            basic_settings=BasicSettings(
                alias=dataDict['extensions'].get('basic_settings', {}).get('alias', ""),
                site_id=dataDict['extensions'].get('basic_settings', {}).get('site_id', "")
            ),
            status_connection=StatusConnection(
                connection=Connection(
                    socket_type=dataDict['extensions'].get('status_connection', {}).get('connection', {}).get('socket_type', "tcp"),
                    host=dataDict['extensions'].get('status_connection', {}).get('connection', {}).get('host', ""),
                    port=dataDict['extensions'].get('status_connection', {}).get('connection', {}).get('port', 0),
                    encrypted=dataDict['extensions'].get('status_connection', {}).get('connection', {}).get('encrypted', True),
                    verify=dataDict['extensions'].get('status_connection', {}).get('connection', {}).get('verify', False)
                ),
                proxy=Proxy(
                    use_livestatus_daemon=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('use_livestatus_daemon', "with_proxy"),
                    global_settings=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('global_settings', False),
                    params=ProxyParams(
                        channels=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('channels', 0),
                        heartbeat=Heartbeat(
                            dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('heartbeat', {}).get('interval', 0),
                            dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('heartbeat', {}).get('timeout', 0),
                        ),
                        channel_timeout=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('channel_timeout', 0),
                        query_timeout=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('query_timeout', 0),
                        connect_retry=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('connect_retry', 0),
                        cache=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('params', {}).get('cache', False)
                    ),
                    tcp=ProxyTCP(
                        port=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('tcp', {}).get('port', 0),
                        only_from=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('tcp', {}).get('only_from', []),
                        tls=dataDict['extensions'].get('status_connection', {}).get('proxy', {}).get('tcp', {}).get('tls', False)
                    )
                ),
                connect_timeout=dataDict['extensions'].get('status_connection', {}).get('connect_timeout', 0),
                persistent_connection=dataDict['extensions'].get('status_connection', {}).get('persistent_connection', False),
                url_prefix=dataDict['extensions'].get('status_connection', {}).get('url_prefix', ""),
                status_host=StatusHost(
                    status_host_set=dataDict['extensions'].get('status_connection', {}).get('status_host', '').get('status_host_set', 'disabled'),
                    host=dataDict['extensions'].get('status_connection', {}).get('status_host', '').get('host', ''),
                    site=dataDict['extensions'].get('status_connection', {}).get('status_host', '').get('site', '')
                ),
                disable_in_status_gui=dataDict['extensions'].get('status_connection', {}).get('disable_in_status_gui', False)
            ),
            configuration_connection=ConfigurationConnection(
                enable_replication=dataDict['extensions'].get('configuration_connection', {}).get('enable_replication', True),
                url_of_remote_site=dataDict['extensions'].get('configuration_connection', {}).get('url_of_remote_site', ""),
                disable_remote_configuration=dataDict['extensions'].get('configuration_connection', {}).get('disable_remote_configuration', True),
                ignore_tls_errors=dataDict['extensions'].get('configuration_connection', {}).get('ignore_tls_errors', False),
                direct_login_to_web_gui_allowed=dataDict['extensions'].get('configuration_connection', {}).get('direct_login_to_web_gui_allowed', True),
                user_sync=UserSync(
                    sync_with_ldap_connections=dataDict['extensions'].get('configuration_connection', {}).get('user_sync', {}).get('sync_with_ldap_connections', {})
                ),
                replicate_event_console=dataDict['extensions'].get('configuration_connection', {}).get('replicate_event_console', True),
                replicate_extensions=dataDict['extensions'].get('configuration_connection', {}).get('replicate_extensions', True)
            )
        )
        return cls(
            links=links,
            domainType=domainType,
            id=id,
            title=title,
            members=members,
            extensions=extensions,
        )


    def createSiteConnection(
            self, 
            cmkAccess=None,
            newSite="",
            ovpnNetwork="",
            ovpnNetworkDomain=""
        ):

        #####################################################################
        ################# Start of internal functions #########################
        #####################################################################
        def createSiteConnection_V2_2(
                cmkAccess=None,
                newSite="",
                ovpnNetwork="",
                ovpnNetworkDomain=""

            ):

            apiUrl=cmkAccess.get_apiUrl()
            requestUrl="/domain-types/site_connection/collections/all"

            linkArray=[]
            
            for methodType in ['GET', 'PUT', 'DELETE']:
                httpReference="http://"+cmkAccess.cmkHostname+"/"+cmkAccess.cmkSite+"/check_mk/api/1.0/objects/site_connection/"+newSite
                if methodType=="GET": rel="self"
                if methodType=="PUT": rel="urn:org.restfulobjects:rels/update"
                if methodType=="DELETE": rel="urn:org.restfulobjects:rels/delete"
                link=Link(domainType="link",
                        href=httpReference,
                        method=methodType,
                        rel=rel,
                        type="application/json"
                )
                linkArray.append(link)

            self.links=linkArray
            self.id=newSite
            self.title=newSite
            self.extensions.basic_settings.alias=newSite
            self.extensions.basic_settings.site_id=newSite
            self.extensions.status_connection.connection.host=newSite+"."+ovpnNetwork+"."+ovpnNetworkDomain
            self.extensions.status_connection.url_prefix="http://"+newSite+"."+ovpnNetwork+"."+ovpnNetworkDomain+"/"
            self.extensions.configuration_connection.url_of_remote_site="http://"+newSite+"."+ovpnNetwork+"."+ovpnNetworkDomain+"/check_mk/"
        
            session = requests.session()
            session.headers['Authorization'] = f"{cmkAccess.credentials}"
            session.headers['Accept'] = 'application/json'
            API_URL=apiUrl+requestUrl
            
            jsonString='{"site_config": '+ \
                json.dumps(self.extensions.to_dict()) + \
            '}'

            payLoad=json.loads(jsonString)

            resp = session.post(apiUrl+requestUrl,
                headers={"Content-Type": 'application/json'},
                json=payLoad
            )
            if resp.status_code == 200:
                response_data=resp.json()
                logger.debug("API request status_code : "+str(resp.status_code))
                logger.debug(str(response_data))
                logger.debug("The following dataDicts are available")
                for dataDict in response_data:
                    logger.debug(str(dataDict)) 

            elif resp.status_code == 204:
                logger.warning("API request status_code : "+str(resp.status_code))
                raise RuntimeWarning(resp.status_code)
            else:
                logger.debug (pprint(resp.__dict__))
                raise RuntimeError(str(resp.json()))    
            return

        def createSiteConnection_V2_3(
                cmkAccess=None,
                newSite="",
                ovpnNetwork="",
                ovpnNetworkDomain=""
            ):

            apiUrl=cmkAccess.get_apiUrl()
            requestUrl="/domain-types/site_connection/collections/all"

            linkArray=[]
            
            for methodType in ['GET', 'PUT', 'DELETE']:
                httpReference="http://"+cmkAccess.cmkHostname+"/"+cmkAccess.cmkSiteName+"/check_mk/api/1.0/objects/site_connection/"+newSite
                if methodType=="GET": rel="self"
                if methodType=="PUT": rel="urn:org.restfulobjects:rels/update"
                if methodType=="DELETE": rel="urn:org.restfulobjects:rels/delete"
                link=Link(domainType="link",
                        href=httpReference,
                        method=methodType,
                        rel=rel,
                        type="application/json"
                )
                linkArray.append(link)

            self.links=linkArray
            self.id=newSite
            self.title=newSite
            self.extensions.basic_settings.alias=newSite
            self.extensions.basic_settings.site_id=newSite
            self.extensions.status_connection.connection.host=newSite+"."+ovpnNetwork+"."+ovpnNetworkDomain
            self.extensions.status_connection.url_prefix="http://"+newSite+"."+ovpnNetwork+"."+ovpnNetworkDomain+"/"
            self.extensions.configuration_connection.url_of_remote_site="http://"+newSite+"."+ovpnNetwork+"."+ovpnNetworkDomain+"/check_mk/"
        
            session = requests.session()
            session.headers['Authorization'] = f"{cmkAccess.credentials}"
            session.headers['Accept'] = 'application/json'
            API_URL=apiUrl+requestUrl
            
            jsonString='{"site_config": '+ \
                json.dumps(self.extensions.to_dict()) + \
            '}'

            payLoad=json.loads(jsonString)

            resp = session.post(apiUrl+requestUrl,
                headers={"Content-Type": 'application/json'},
                json=payLoad
            )
            if resp.status_code == 200:
                response_data=resp.json()
                logger.debug("API request status_code : "+str(resp.status_code))
                logger.debug(str(response_data))
                logger.debug("The following dataDicts are available")
                for dataDict in response_data:
                    logger.debug(str(dataDict)) 

            elif resp.status_code == 204:
                logger.warning("API request status_code : "+str(resp.status_code))
                raise RuntimeWarning(resp.status_code)
            else:
                logger.debug (pprint.pprint(resp.__dict__))
                raise RuntimeError(str(resp.json()))    
            return
        #####################################################################
        ################# end of internal functions #########################
        #####################################################################




        if not isinstance(cmkAccess,RestAPIcredentials): 
            logger.error("cmkAccess is not of type RestAPIcredentials")
            raise ValueError("cmkAccess is not of type RESTAPIcredentials")

        cmkVersion=str(VERSION.checkmk_version)
        if cmkVersion.startswith("2.2."):
            createSiteConnection_V2_2(
                cmkAccess=cmkAccess,
                newSite=newSite,
                ovpnNetwork=ovpnNetwork,
                ovpnNetworkDomain=ovpnNetworkDomain
            )
        elif cmkVersion.startswith("2.3."):
            createSiteConnection_V2_3(
                cmkAccess=cmkAccess,
                newSite=newSite,
                ovpnNetwork=ovpnNetwork,
                ovpnNetworkDomain=ovpnNetworkDomain
            )
        else:
            logger.error("cmkVersion is not supported")
            raise ValueError("cmkVersion is not supported")
        return


    def updateSiteConnection(
            self, 
            cmkAccess=None
        ):

        if not isinstance (cmkAccess, RestAPIcredentials):
            raise ValueError("cmkAccess is not of type RestAPIcredentials")
        apiUrl=cmkAccess.get_apiUrl()   
        requestUrl="/objects/site_connection/"+self.id
       
        session = requests.session()
        session.headers['Authorization'] = f"{cmkAccess.credentials}"
        session.headers['Accept'] = 'application/json'
        API_URL=apiUrl+requestUrl
        
        jsonString='{"site_config": '+ \
            json.dumps(self.extensions.to_dict()) + \
        '}'

        payLoad=json.loads(jsonString)
        logger.debug (pprint.pformat(jsonString,indent=4))

        resp = session.put(
            f"{API_URL}",
            headers={"Content-Type": 'application/json'},
            json=payLoad
        )
        if resp.status_code == 200:
            pass
        elif resp.status_code == 204:
            logger.warning("API request status_code : "+str(resp.status_code))
            raise RuntimeWarning(resp.status_code)
        else:
            logger.debug (pprint.pformat(resp.__dict__),indent=4)
            raise RuntimeError(str(resp.json()))    


        return

class SiteAllConnections:
    def __init__(self,cmkAccess=None):
        if cmkAccess == None: raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials: raise ValueError("cmkAccess are not of type RESTAPIcredentials")
        
        apiUrl=cmkAccess.get_apiUrl()
        requestUrl="/domain-types/site_connection/collections/all"

        self._links=[]
        self._domainType=""
        self._id=""
        self._title=""
        self._value=[]

        session = requests.session()
        session.headers['Authorization'] = cmkAccess.credentials
        session.headers['Accept'] = 'application/json'

        resp = session.get(apiUrl+requestUrl)
        if resp.status_code == 200:
            response_data=resp.json()
            logger.info ("Successfully read all Site Connections")
            logger.info ("API request status_code : "+str(resp.status_code))

        elif resp.status_code == 204:
            logger.warning("API request status_code : "+str(resp.status_code))
            raise RuntimeWarning(resp.status_code)
        else:
            raise RuntimeError(print(resp.json()))    
        
        
        linkArray=[]
        for linkDataDict in response_data.get('links', []):
            link=Link(domainType=linkDataDict.get('domainType',''),
                      href=linkDataDict.get('href',''),
                      method=linkDataDict.get('method',''),
                      rel=linkDataDict.get('rel',''),
                      type=linkDataDict.get('type','')
            )
            linkArray.append(link)
        self._links=linkArray
        
        self._id=response_data.get('id', ""),
        self._domainType=response_data.get('domainType', ""),
        self._title=response_data.get('title', ""),
        
        for dataDict in response_data.get('value', []):
            site_connection=SiteConnection.from_dict(dataDict=dataDict)
            self._value.append(site_connection)
    
        self._extensions=response_data.get('extensions', {})
    
    @property
    def links(self):
        return self._links

    @links.setter
    def links(self, value):
        self._links = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def domainType(self):
        return self._domainType

    @domainType.setter
    def domainType(self, value):
        self._domainType = value

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        self._title = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    @property
    def extensions(self):
        return self._extensions

    @extensions.setter
    def extensions(self, value):
        self._extensions = value

    @property
    def requestUrl(self):
        return self._requestUrl
    
    @requestUrl.setter
    def requestUrl(self,value):
        self._requestUrl=value

    
    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "id": self._id,
            "domainType": self._domainType,
            "title": self._title,
            "value": [val.to_dict() for val in self._value],
            "extensions": self._extensions
        }

    def getConnectedSiteIDs(self):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))

        connectionsIDs=[]
        for site in self._value:
            connectionsIDs.append(site.id)

        logger.debug("Leaving function "+str(function_name))
        return connectionsIDs

    def getConnectedSite(self,siteID):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))

        returnSite=None
        for site in self._value:
            logger.debug("Checking site with ID "+str(site.id)+" and comparing with given ID "+str(siteID))
            if site.id == siteID:
                returnSite=site
                logger.debug("Found site with ID "+str(site.id))
                break
        if returnSite is None:
            logger.error("Site with ID "+str(siteID)+" not found")
            raise ResourceWarning("Site with ID "+str(siteID)+" not found")
        
        logger.debug("Leaving function "+str(function_name))
        return returnSite

class AllActivationsExtensions:
    def __init__(self, 
                 changes=[], 
                 is_running=False, 
                 activate_foreign=False, 
                 time_started=""
        ):
         
        self._changes=changes
        self._is_running=is_running
        self._activate_foreign=activate_foreign
        self._time_started=time_started

    @property
    def changes(self):
        return self._changes
    
    @changes.setter
    def changes(self, value):
        self._changes = value

    @property
    def is_running(self):
        return self._is_running
    
    @is_running.setter
    def is_running(self, value):
        self._is_running = value

    @property
    def activate_foreign(self):
        return self._activate_foreign
    
    @activate_foreign.setter
    def activate_foreign(self, value):
        self._activate_foreign = value

    @property   
    def time_started(self):
        return self._time_started
    @time_started.setter
    def time_started(self, value):
        self._time_started = value  

    @ classmethod
    def from_dict(cls,dataDict=None):

        cls=cls() 
        if dataDict is None:
            raise ValueError("dataDict is None")
        
        cls.changes=[]
        for changeDataDict in dataDict.get('links', []):
            change=Change(
                id=changeDataDict.get('id',''),
                action_name=changeDataDict.get('action_name',''),
                text=changeDataDict.get('text',''),
                user_id=changeDataDict.get('user_id',''),
                time=changeDataDict.get('time','')
            )
            cls.changes.append(change)

        cls.is_running=dataDict.get('is_running', False)
        cls.activate_foreign=dataDict.get('activate_foreign', False)
        cls.time_started=dataDict.get('time_started', "")
        return cls

    def to_dict(self):
        return {
            "changes": [change.to_dict() for change in self._changes],
            "is_running": self._is_running,
            "activate_foreign": self._activate_foreign,
            "time_started": self._time_started
        }    

class Change:
    def __init__(self, 
                 id="", 
                 action_name="", 
                 text="", 
                 user_id="", 
                 time=""
        ):
         
        self._id = id
        self._action_name = action_name
        self._text = text
        self._user_id = user_id
        self._time = time

    @property
    def id(self):
        return self._id
    
    @id.setter
    def id(self, value):
        self._id = value
    
    @property
    def action_name(self):
        return self._action_name
    
    @action_name.setter
    def action_name(self, value):
        self._action_name = value
    @property
    def text(self):
        return self._text
    
    @text.setter
    def text(self, value):
        self._text = value
    
    @property
    def user_id(self):
        return self._user_id
    
    @user_id.setter
    def user_id(self, value):
        self._user_id = value

    @property
    def time(self):
        return self._time
    
    @time.setter
    def time(self, value):
        self._time = value
    
    def to_dict(self):
        return {
            "id": self._id,
            "action_name": self._action_name,
            "text": self._text,
            "user_id": self._user_id,
            "time": self._time
        }

    def map_dataDict_to_Change(self, dataDict):
        
        change=Change(
            id=dataDict["id"],
            action_name=dataDict["action_name"],
            text=dataDict["text"],
            user_id=dataDict["user_id"],
            time=dataDict["time"]
        )
        return change

class AllActivations:
    def __init__(self,
                 cmkAccess=None
        ):
        logger.debug("Entering function "+str(inspect.currentframe().f_code.co_name))
        logger.debug("cmkAccess: "+str(cmkAccess))
        if cmkAccess == None: raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials: raise ValueError("cmkAccess are not of type RESTAPIcredentials")
        
        self._links=[]
        self._domainType=""
        self._id=""
        self._title=""
        self._members={}
        self._retryActivationCount=0
        self.loadPendingChanges(cmkAccess)     
    
    @property
    def links(self):
        return self._links
    @links.setter
    def links(self, value):
        self._links = value

    @property
    def domainType(self):
        return self._domainType
    @domainType.setter
    def domainType(self, value):
        self._domainType = value

    @property
    def id(self):
        return self._value
    @id.setter
    def value(self, value):
        self._id = value

    @property
    def title(self):
        return self._title
    @title.setter
    def title(self, value):
        self._title = value

    @property
    def members(self):
        return self._members
    @members.setter
    def members(self, value):
        self._members = value

    @property
    def extensions(self):
        return self._extensions
    @extensions.setter
    def extensions(self, value):
        self._extensions = value


    def loadPendingChanges(self,cmkAccess):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))

        if not isinstance(cmkAccess, RestAPIcredentials): raise ValueError("cmkAccess is not of type RestAPIcredentials")

        apiUrl=cmkAccess.get_apiUrl()
        requestUrl="/domain-types/activation_run/collections/pending_changes"

        self._links=None
        self._domainType=""
        self._value=[]
        self._id=""
        self._title=""
        self._members={}
        self._extensions=AllActivationsExtensions()

        session = requests.session()
        session.headers['Authorization'] = cmkAccess.credentials
        session.headers['Accept'] = 'application/json'

        resp = session.get(apiUrl+requestUrl)
        if resp.status_code == 200:
            response_data=resp.json()
            logger.info ("Successfully read all Site Connections")
            logger.info ("API request status_code : "+str(resp.status_code))

        elif resp.status_code == 403:
            logger.warning("Configuration via setup is disabled -- API request status_code : "+str(resp.status_code))
            raise RuntimeWarning(resp.status_code)
        elif resp.status_code == 406:
            logger.warning("The requests accept headers can not be satisfied : "+str(resp.status_code))
            raise RuntimeWarning(resp.status_code)
        else:
            raise RuntimeError(print(resp.json()))    
        
        
        self._ETag=resp.headers["ETag"]
        self.from_dict_pendingChanges(dataDict=response_data)

        logger.debug("Leaving function "+str(function_name))
        return

    def from_dict_pendingChanges(self, dataDict=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))

        
        self._links=dataDict.get('links', None)
        self._domainType=dataDict.get('domainType', "")
        self._id=dataDict.get('id', "")
        self._title=dataDict.get('title', "")
        self._members=dataDict.get('members', {})
        for value in dataDict.get('value', []):
            change=Change().map_dataDict_to_Change(value)
            self._value.append(change)
        extensions=dataDict.get('extensions', {})
        if extensions != {}:
            self._extensions.from_dict(extensions)
        else:
            self._extensions=extensions

        logger.debug("Leaving function "+str(function_name))
        return 

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "domainType": self._domainType,
            "id": self._id,
            "title": self._title,
            "members": self._members,
            "value": [activation.to_dict() for activation in self._value],
            "extensions": self._extensions.to_dict()
        }

    def activatePendingChanges(self, cmkAccess=None, redirect=True, sites=[], force_foreign_changes=False):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function "+str(function_name))
        
        if cmkAccess == None: raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials: raise ValueError("cmkAccess are not of type RESTAPIcredentials")

        apiUrl=cmkAccess.get_apiUrl()
        requestUrl="/domain-types/activation_run/actions/activate-changes/invoke"

        session = requests.session()
        session.headers['Authorization'] = f"{cmkAccess.credentials}"
        session.headers['Accept'] = 'application/json'
        session.headers['If-Match'] = f"{self._ETag}"

        payLoad=dict()
        payLoad["redirect"]=redirect
        payLoad["sites"]=sites
        payLoad["force_foreign_changes"]=force_foreign_changes

        resp = session.post(apiUrl+requestUrl,json=payLoad)
        if resp.status_code in [200]:
            response_data=resp.json()
            logger.debug("API request status_code : "+str(resp.status_code))
            logger.debug(str(response_data))
            activationResponse="Started"
        elif resp.status_code == 204:
            logger.info("Activation completed successfully")
            activationResponse="Done"
        elif resp.status_code == 409:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("Conflict        : Some sites could not be activated.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            activationResponse=resp.status_code
        elif resp.status_code == 412:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("The list of Activations changed")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            activationResponse=resp.status_code
            if self._retryActivationCount <= 3:
                self._retryActivationCount+=1
                logger.warning("Reloading the list of Activations")
                self.loadPendingChanges(cmkAccess)
                activationResponse=self.activatePendingChanges(cmkAccess, redirect, sites, force_foreign_changes)
        elif resp.status_code == 422:
            problemDetails=resp.json()
            logger.warning(function_name+" responded:")
            logger.warning("No pending activations.")
            logger.warning("API status code : "+str(resp.status_code))
            logger.warning("Response title  : "+str(problemDetails.get('title',"")))
            logger.warning("Response details: "+str(problemDetails.get('details',"")))
            activationResponse=resp.status_code
        else:
            logger.error(print(resp.json()))
            logger.error("API request status_code : "+str(resp.status_code))      
            raise RuntimeError(function_name+" failed")
        
        logger.debug("Leaving function "+str(function_name))
        return activationResponse


