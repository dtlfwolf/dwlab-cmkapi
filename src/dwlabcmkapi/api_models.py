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


class Hosts:
    def __init__(
        self,
        links=None,
        id="",
        disabledReason="",
        invalidReason="",
        x_ro_invalidReason="",
        memberType="",
        value=None,
        name="",
        title="",
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

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "id": self._id,
            "disabledReason": self._disabledReason,
            "invalidReason": self._invalidReason,
            "x_ro_invalidReason": self._x_ro_invalidReason,
            "memberType": self._memberType,
            "value": [value.to_dict() for value in self._value],
            "title": self._title,
        }


class Move:
    def __init__(
        self,
        links=None,
        id="",
        disabledReason="",
        invalidReason="",
        x_ro_invalidReason="",
        memberType="",
        parameters=None,
        name="",
        title="",
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

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "id": self._id,
            "disabledReason": self._disabledReason,
            "invalidReason": self._invalidReason,
            "x_ro_invalidReason": self._x_ro_invalidReason,
            "memberType": self._memberType,
            "parameters": self._parameters,
            "name": self._name,
            "title": self._title,
        }


class FolderConfigMembers:
    def __init__(self, hosts=None, move=None):
        self._hosts = hosts if hosts is not None else Hosts()
        self._move = move if move is not None else Move()

    def to_dict(self):
        return {"hosts": self._hosts.to_dict(), "move": self._move.to_dict()}


class FolderExtensions:
    def __init__(self, path="/", attributes=None):
        self._path = path
        self._attributes = attributes if attributes is not None else {}

    def to_dict(self):
        return {"path": self._path, "attributes": self._attributes}


class FolderConfig:
    def __init__(self, links=None, domainType="", id="", title="", members=None, extensions=None):
        self._links = links if links is not None else []
        self._domainType = domainType
        self._id = id
        self._title = title
        self._members = members if members is not None else FolderConfigMembers()
        self._extensions = extensions if extensions is not None else FolderExtensions()

    def to_dict(self):
        return {
            "links": [link.to_dict() for link in self._links],
            "domainType": self._domainType,
            "id": self._id,
            "title": self._title,
            "members": self._members.to_dict(),
            "extensions": self._extensions.to_dict(),
        }


class Members:
    def __init__(self, folder_config=None):
        self._folder_config = folder_config if folder_config is not None else FolderConfig()

    def to_dict(self):
        return {"folder_config": self._folder_config.to_dict()}
