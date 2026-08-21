from dwlabcmkapi.api_client import CheckmkRestClient


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response):
        self.headers = {}
        self._response = response
        self.calls = []
        self.closed = False
        self.verify = True

    def request(self, method, url, json=None, timeout=None):
        self.calls.append((method, url, json, dict(self.headers), timeout))
        return self._response

    def close(self):
        self.closed = True


def test_rest_client_uses_base_url_headers_and_closes_session():
    response = _FakeResponse()
    session = _FakeSession(response)
    client = CheckmkRestClient(
        base_url="https://cmk.example.org/main/check_mk/api/2.3",
        authorization="Bearer token",
        session_factory=lambda: session,
    )

    returned = client.post(
        "/objects/test",
        json_body={"hello": "world"},
        headers={"If-Match": "abc"},
    )

    assert returned is response
    assert session.closed is True
    assert session.calls == [
        (
            "POST",
            "https://cmk.example.org/main/check_mk/api/2.3/objects/test",
            {"hello": "world"},
            {
                "Authorization": "Bearer token",
                "Accept": "application/json",
                "If-Match": "abc",
            },
            10.0,
        )
    ]


def test_rest_client_can_be_built_from_credentials():
    class FakeCredentials:
        credentials = "Bearer abc"

        def get_apiUrl(self, apiVersion=""):
            assert apiVersion == "1.0.0"
            return "https://central.example.org/main/check_mk/api/1.0.0"

    client = CheckmkRestClient.from_credentials(FakeCredentials(), api_version="1.0.0")

    assert client.base_url == "https://central.example.org/main/check_mk/api/1.0.0"
    assert client.authorization == "Bearer abc"


def test_rest_client_sets_explicit_verify_bundle():
    response = _FakeResponse()
    session = _FakeSession(response)
    client = CheckmkRestClient(
        base_url="https://cmk.example.org/main/check_mk/api/2.3",
        authorization="Bearer token",
        session_factory=lambda: session,
        verify="/etc/ssl/certs/ca-certificates.crt",
    )

    client.get("/version")

    assert session.verify == "/etc/ssl/certs/ca-certificates.crt"


def test_rest_client_uses_explicit_timeout():
    response = _FakeResponse()
    session = _FakeSession(response)
    client = CheckmkRestClient(
        base_url="https://cmk.example.org/main/check_mk/api/2.3",
        authorization="Bearer token",
        session_factory=lambda: session,
        timeout=3.5,
    )

    client.get("/version")

    assert session.calls == [
        (
            "GET",
            "https://cmk.example.org/main/check_mk/api/2.3/version",
            None,
            {
                "Authorization": "Bearer token",
                "Accept": "application/json",
            },
            3.5,
        )
    ]
