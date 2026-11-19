"""No secret files, environment proxies, redirects or partial published agents."""

from pathlib import Path

import pytest
import requests

from dwlabcmkapi.agent_download import LocalAgentDownloader
from dwlabcmkapi.credential_bootstrap import BootstrapError, RootBootstrapAuthorization
from dwlabcmkapi.credential_provider import AutomationCredential


class Provider:
    def find_ready(self, path, site):
        return AutomationCredential("dwlab-automation", "private-test-secret")


class Response:
    def __init__(self, status=200, name=None, content=b"agent"):
        self.status_code = status
        self.headers = {"Content-Disposition": 'attachment; filename="' + name + '"'} if name else {}
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def json(self):
        return {"site": "client"}

    def iter_content(self, size):
        yield self.content


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.trust_env = True
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert "Authorization" in self.headers
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def authorization(monkeypatch):
    monkeypatch.setattr(RootBootstrapAuthorization, "require_root", lambda _: None)


def test_downloads_use_loopback_no_proxy_and_no_redirects(tmp_path):
    session = Session([Response(), Response(name="agent.deb"), Response(name="agent.rpm"), Response(name="agent.msi")])
    LocalAgentDownloader(Provider(), lambda: session).download("client", Path("/private/ref"), 8080, tmp_path)
    assert not session.trust_env
    assert {p.name for p in tmp_path.iterdir()} == {"agent.deb", "agent.rpm", "agent.msi"}
    assert all(url.startswith("http://127.0.0.1:8080/client/") for url, _ in session.calls)
    assert all(kwargs["allow_redirects"] is False for _, kwargs in session.calls)
    assert not (tmp_path / ".netrc").exists()


@pytest.mark.parametrize("status", [301, 302, 401, 403])
def test_auth_failure_and_redirect_are_terminal(tmp_path, status):
    session = Session([Response(status)])
    with pytest.raises(BootstrapError):
        LocalAgentDownloader(Provider(), lambda: session).download("client", Path("/private/ref"), 8080, tmp_path)
    assert len(session.calls) == 1


@pytest.mark.parametrize("name", ["../../secret.deb", "/tmp/secret.deb", "agent.sh", "a\nb.deb"])
def test_unsafe_download_filenames_rejected_without_publish(tmp_path, name):
    session = Session([Response(), Response(name=name)])
    with pytest.raises(BootstrapError):
        LocalAgentDownloader(Provider(), lambda: session).download("client", Path("/private/ref"), 8080, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_failed_later_agent_preserves_existing_artifacts(tmp_path):
    (tmp_path / "previous.deb").write_bytes(b"previous")
    session = Session([Response(), Response(name="new.deb"), Response(500)])
    with pytest.raises(BootstrapError):
        LocalAgentDownloader(Provider(), lambda: session).download("client", Path("/private/ref"), 8080, tmp_path)
    assert list(p.name for p in tmp_path.iterdir()) == ["previous.deb"]


def test_wait_is_bounded_without_swallowing_safety_errors(tmp_path):
    class Pending:
        def find_ready(self, path, site):
            return None

    times = iter([0, 100])
    with pytest.raises(BootstrapError, match="Timed out"):
        LocalAgentDownloader(Pending(), clock=lambda: next(times)).download(
            "client", Path("/private/ref"), 8080, tmp_path, timeout=1)


def test_restart_after_readiness_retries_the_whole_batch_without_partial_publish(tmp_path):
    (tmp_path / "previous.deb").write_bytes(b"previous")
    session = Session([Response(), Response(name="discard.deb"), requests.ConnectionError("restart"),
                       Response(), Response(name="agent.deb"), Response(name="agent.rpm"), Response(name="agent.msi")])
    sleeps = []

    def sleep(delay):
        assert sorted(p.name for p in tmp_path.iterdir()) == ["previous.deb"]
        sleeps.append(delay)

    LocalAgentDownloader(Provider(), lambda: session, sleep=sleep).download(
        "client", Path("/private/ref"), 8080, tmp_path)
    assert sleeps == [5]
    assert {p.name for p in tmp_path.iterdir()} == {"previous.deb", "agent.deb", "agent.rpm", "agent.msi"}


def test_repeated_transport_failure_is_bounded(tmp_path):
    session = Session([Response(), requests.ConnectionError("restart")])
    now = [0]

    def sleep(delay):
        now[0] += delay

    with pytest.raises(BootstrapError, match="Timed out"):
        LocalAgentDownloader(Provider(), lambda: session, clock=lambda: now[0], sleep=sleep).download(
            "client", Path("/private/ref"), 8080, tmp_path, timeout=1)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("status", [301, 401, 403, 500])
def test_batch_authentication_redirect_and_server_errors_are_not_transient(tmp_path, status):
    session = Session([Response(), Response(status)])
    with pytest.raises(BootstrapError):
        LocalAgentDownloader(Provider(), lambda: session).download("client", Path("/private/ref"), 8080, tmp_path)
    assert len(session.calls) == 2
    assert not list(tmp_path.iterdir())


def test_tls_failure_is_never_retried(tmp_path):
    session = Session([Response(), requests.exceptions.SSLError("untrusted")])
    with pytest.raises(requests.exceptions.SSLError):
        LocalAgentDownloader(Provider(), lambda: session).download("client", Path("/private/ref"), 8080, tmp_path)
    assert len(session.calls) == 2
