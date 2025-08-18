from pathlib import Path
import sys
from dwlab_cmkapi import cmk_RESTAPI

import logging
from dwlab_basicpy import dwlabLogger
dwlabLogger.setup_logging()
logger=logging.getLogger(__name__)

class cmkCentralSite:
    def __init__(self,
                 cmkSiteName="",
                 centralHostname="",
                 centralDomain="",
                 ovpnNetwork=None,
                 ovpnNetworkDomain=None,
                 cmkAccess=None
                 ):
        function_name = sys._getframe().f_code.co_name
        class_name=self.__class__.__name__
        function_name=class_name+"."+function_name
        logger.debug("Entering function "+str(function_name))

        if not isinstance(cmkAccess, cmk_RESTAPI.RestAPIcredentials):
            raise TypeError("Credentials must be an instance of RestAPIcredentials")
        else:
            self._cmkAccess=cmkAccess
            logger.debug("cmkAccess is an instance of RestAPIcredentials")
            logger.debug("cmkAccess is: "+str(cmkAccess))
        if not isinstance(cmkSiteName, str):
            raise TypeError("cmkSiteName must be a string")
        else:
            self._cmkSiteName=cmkSiteName
            logger.debug("cmkSiteName is: "+str(cmkSiteName))
        if not isinstance(centralHostname, str):
            raise TypeError("centralHostname must be a string")
        else:
            self._centralHostname=centralHostname
            logger.debug("centralHostnameis: "+str(centralHostname))
        if not isinstance(centralDomain, str):
            raise TypeError("centralDomain must be a string")
        else:
            self._centralDomain=centralDomain
            logger.debug("centralDomain is: "+str(centralDomain))
        if not isinstance(ovpnNetwork, str):
            raise TypeError("ovpnNetwork must be a string")
        else:
            self._ovpnNetwork=ovpnNetwork
            logger.debug("ovpnNetwork is: "+str(ovpnNetwork))
        if not isinstance(ovpnNetworkDomain, str):
            raise TypeError("ovpnNetworkDomain must be a string")
        else:
            self._ovpnNetworkDomain=ovpnNetworkDomain
            logger.debug("ovpnNetworkDomain is: "+str(ovpnNetworkDomain))
        

    @property
    def cmkSiteName(self):
        return self._cmkSiteName

    @property
    def centralHostname(self):
        return self._centralHostname
    
    @property 
    def centralDomain(self):
        return self._centralDomain
    
    @property
    def version(self):
        return self._version
    @property
    def apiVersion(self):
        return self._version.apiVersion
    @property
    def checkmkVersion(self):
        return self._version.checkmkVersion
    @property
    def ovpnNetwork(self):
        return self._ovpnNetwork
    @property
    def ovpnNetworkDomain(self):
        return self._ovpnNetworkDomain
    @property
    def cmkAccess(self):
        return self._cmkAccess



    def catalogSite(self, instanceName=None):
        function_name = sys._getframe().f_code.co_name
        class_name=self.__class__.__name__
        function_name=class_name+"."+function_name
        logger.debug("Entering function "+str(function_name))

        if not isinstance(instanceName, str):
            raise TypeError("instanceName must be a string")
        if instanceName == "":
            raise ValueError("instanceName cannot be empty")

        new_host=str(instanceName)+"."+str(self._ovpnNetwork)+"."+str(self._ovpnNetworkDomain)
        
        try:
            logger.debug("Getting host config for "+new_host)
            host_config=cmk_RESTAPI.HostConfig.ShowHost(
                requestedHost=new_host,
                cmkAccess=self._cmkAccess
            )
        except Exception as e:
            logger.error("cmk_RESTAPI.HostConfig.ShowHost failed for some reason.")
            logger.error("The following exception occured:")
            logger.error(str(e.args[0]))
            raise e


        if host_config==None:
            try:
                logger.debug("Host config for "+new_host+" not found.")
                logger.debug("Creating new host "+new_host)
                host_config=cmk_RESTAPI.HostConfig.CreateHost(
                    newHost=new_host,
                    folder="/",
                    cmkAccess=self._cmkAccess
                )
            except Exception as e:
                logger.error("New site "+new_host+" was not created.")
                logger.error("The following exception occured:")
                logger.error(str(e.args[0]))
                raise RuntimeError("New site "+new_host+" was not created.")
        
            try:
                logger.debug("Activating host "+new_host)
                logger.debug("self._cmkAccess is: "+str(self._cmkAccess))
                activation=cmk_RESTAPI.AllActivations(cmkAccess=self._cmkAccess)
                try:
                    logger.debug("Now holding all pending changes and trying to activate these changes.")
                    activationResponse=activation.activatePendingChanges(cmkAccess=self._cmkAccess)
                except Exception as e:
                    logger.error("The host "+new_host+" has not been activated successfully.")
                    logger.error("The following exception occured:")
                    logger.error(str(e.args[0]))
                    raise RuntimeError("The host "+new_host+" has not been activated successfully.")
            except Exception as e:
                logger.error("cmk_RESTAPI.AllActivations failed for some reason.")
                logger.error("The following exception occured:")
                logger.error(str(e.args[0]))
                activationResponse=""
                
            
            if isinstance (activationResponse,str) and activationResponse in ["Done", "Started"]:
                logger.debug("Host "+new_host+" has been activated. Now trying to discover it to make sure it is available.")
                try:
                    serviceDiscovery=host_config.executeDiscovery(cmkAccess=self._cmkAccess)
                except Exception as e:
                    logger.error("The host "+new_host+" has not been discovered successfully.")
                    logger.error("The following exception occured:")
                    logger.error(str(e.args[0]))

                try:
                    activation=cmk_RESTAPI.AllActivations(cmkAccess=self._cmkAccess)
                    activationResponse=activation.activatePendingChanges(cmkAccess=self._cmkAccess)
                except Exception as e:
                    logger.error("The host "+new_host+" has not been activated successfully.")
                    logger.error("The following exception occured:")
                    logger.error(str(e.args[0]))
                logger.info("The host "+new_host+" has been activated successfully.")

        try:
            allSiteConnections=cmk_RESTAPI.SiteAllConnections(cmkAccess=self._cmkAccess)

            if instanceName not in allSiteConnections.getConnectedSiteIDs():
                logger.info("New site "+instanceName+" is not cataloged yet.")

                # This is a new site
                try:
                    logger.info("Creating new site connection for "+instanceName)
                    new_siteConnection=cmk_RESTAPI.SiteConnection()
                    
                    new_siteConnection.createSiteConnection(
                        cmkAccess=self._cmkAccess,
                        newSite=instanceName,
                        ovpnNetwork=self._ovpnNetwork,
                        ovpnNetworkDomain=self._ovpnNetworkDomain
                    )
                except Exception as e:
                    logger.error("cmk_RESTAPI.SiteConnection.createSiteConnection failed for some reason.")
                    logger.error("The following exception occured:")
                    logger.error(str(e.args[0]))
                    raise RuntimeError("cmk_RESTAPI.SiteConnection.createSiteConnection failed for some reason.")

            # This is an existing site
            logger.debug("The site "+instanceName+" should exist now.")
            allSiteConnections=cmk_RESTAPI.SiteAllConnections(cmkAccess=self._cmkAccess)
            # Is the status_host defined?
            logger.debug("Checking if the status_host is defined.")
            try:
                existingSiteConnection=allSiteConnections.getConnectedSite(instanceName)
                if existingSiteConnection.extensions.status_connection.status_host.status_host_set=="enabled":
                    logger.info("New site "+instanceName+" is already cataloged.")
                    logger.info("The status_host is already defined.")
                else:
                    logger.info("New site "+instanceName+" is already cataloged.")
                    logger.info("The status_host is not defined.")
                    # check for the existing host
                    statusHost=cmk_RESTAPI.HostConfig.ShowHost(
                        requestedHost=new_host,
                        cmkAccess=self._cmkAccess
                    )
                    if statusHost is not None:
                        logger.info("New host "+new_host+" is available.")
                        logger.info("Adding new host as status_host "+self._cmkSiteName+" for the status_connection.")
                        existingSiteConnection.extensions.status_connection.status_host.host=new_host
                        existingSiteConnection.extensions.status_connection.status_host.status_host_set="enabled"
                        existingSiteConnection.extensions.status_connection.status_host.site=self._cmkSiteName
                        existingSiteConnection.updateSiteConnection(
                            cmkAccess=self._cmkAccess
                        )
            except:
                logger.error("The site "+instanceName+" can't be found.")
                raise RuntimeError("The site "+instanceName+" can't be found.")
        except Exception as e:
            logger.error("The following exception occured:")
            logger.error(str(e.args[0]))
            raise e

        logger.info("New site "+instanceName+" was created.")

        logger.debug("Leaving function "+str(function_name))
        return 



