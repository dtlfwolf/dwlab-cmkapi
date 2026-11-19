"""No secret files, environment proxies, redirects or partial published agents."""

from pathlib import Path

import pytest

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
        return next(self.responses)


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
