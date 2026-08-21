import inspect
import logging

from .api_credentials import RestAPIcredentials
from .operations import ActivationGateway

logger = logging.getLogger(__name__)


class AllActivationsExtensions:
    def __init__(self, changes=None, is_running=False, activate_foreign=False, time_started=""):
        self._changes = changes if changes is not None else []
        self._is_running = is_running
        self._activate_foreign = activate_foreign
        self._time_started = time_started

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

    @classmethod
    def from_dict(cls, dataDict=None):
        instance = cls()
        if dataDict is None:
            raise ValueError("dataDict is None")

        instance.changes = []
        for changeDataDict in dataDict.get("links", []):
            change = Change(
                id=changeDataDict.get("id", ""),
                action_name=changeDataDict.get("action_name", ""),
                text=changeDataDict.get("text", ""),
                user_id=changeDataDict.get("user_id", ""),
                time=changeDataDict.get("time", ""),
            )
            instance.changes.append(change)

        instance.is_running = dataDict.get("is_running", False)
        instance.activate_foreign = dataDict.get("activate_foreign", False)
        instance.time_started = dataDict.get("time_started", "")
        return instance

    def to_dict(self):
        return {
            "changes": [change.to_dict() for change in self._changes],
            "is_running": self._is_running,
            "activate_foreign": self._activate_foreign,
            "time_started": self._time_started,
        }


class Change:
    def __init__(self, id="", action_name="", text="", user_id="", time=""):
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
            "time": self._time,
        }

    def map_dataDict_to_Change(self, dataDict):
        return Change(
            id=dataDict["id"],
            action_name=dataDict["action_name"],
            text=dataDict["text"],
            user_id=dataDict["user_id"],
            time=dataDict["time"],
        )


class AllActivations:
    def __init__(self, cmkAccess=None):
        logger.debug("Entering function " + str(inspect.currentframe().f_code.co_name))
        logger.debug("cmkAccess: " + str(cmkAccess))
        if cmkAccess is None:
            raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials:
            raise ValueError("cmkAccess are not of type RESTAPIcredentials")

        self._links = []
        self._domainType = ""
        self._id = ""
        self._title = ""
        self._members = {}
        self._retryActivationCount = 0
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

    def loadPendingChanges(self, cmkAccess):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        if not isinstance(cmkAccess, RestAPIcredentials):
            raise ValueError("cmkAccess is not of type RestAPIcredentials")

        self._links = None
        self._domainType = ""
        self._value = []
        self._id = ""
        self._title = ""
        self._members = {}
        self._extensions = AllActivationsExtensions()

        self._ETag, response_data = ActivationGateway(cmkAccess).load_pending_changes()
        self.from_dict_pendingChanges(dataDict=response_data)

        logger.debug("Leaving function " + str(function_name))

    def from_dict_pendingChanges(self, dataDict=None):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        self._links = dataDict.get("links", None)
        self._domainType = dataDict.get("domainType", "")
        self._id = dataDict.get("id", "")
        self._title = dataDict.get("title", "")
        self._members = dataDict.get("members", {})
        for value in dataDict.get("value", []):
            change = Change().map_dataDict_to_Change(value)
            self._value.append(change)
        extensions = dataDict.get("extensions", {})
        if extensions != {}:
            self._extensions.from_dict(extensions)
        else:
            self._extensions = extensions

        logger.debug("Leaving function " + str(function_name))

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "domainType": self._domainType,
            "id": self._id,
            "title": self._title,
            "members": self._members,
            "value": [activation.to_dict() for activation in self._value],
            "extensions": self._extensions.to_dict(),
        }

    def activatePendingChanges(self, cmkAccess=None, redirect=True, sites=None, force_foreign_changes=False):
        function_name = inspect.currentframe().f_code.co_name
        logger.debug("Entering function " + str(function_name))

        if sites is None:
            sites = []
        if cmkAccess is None:
            raise ValueError("cmkAccess is empty")
        if type(cmkAccess) != RestAPIcredentials:
            raise ValueError("cmkAccess are not of type RESTAPIcredentials")

        activationResponse = ActivationGateway(cmkAccess).activate_pending_changes(
            etag=self._ETag,
            redirect=redirect,
            sites=sites,
            force_foreign_changes=force_foreign_changes,
        )
        if activationResponse == 412 and self._retryActivationCount <= 3:
            self._retryActivationCount += 1
            logger.warning("Reloading the list of Activations")
            self.loadPendingChanges(cmkAccess)
            activationResponse = self.activatePendingChanges(cmkAccess, redirect, sites, force_foreign_changes)

        logger.debug("Leaving function " + str(function_name))
        return activationResponse
