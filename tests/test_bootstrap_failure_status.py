"""Private, allowlisted fatal bootstrap status fails installers promptly."""

from dataclasses import replace
from pathlib import Path
import json

import pytest

from dwlabcmkapi.credential_bootstrap import BootstrapError, BootstrapFailureCode, SiteCredentialStore, SiteCredentialState
from dwlabcmkapi.credential_provider import SiteAutomationCredentialProvider
from dwlabcmkapi.agent_download import LocalAgentDownloader


@pytest.fixture(autouse=True)
def root(monkeypatch):
    monkeypatch.setattr("dwlabcmkapi.credential_bootstrap.RootBootstrapAuthorization.require_root", lambda self: None)


def test_failure_is_private_site_bound_and_never_contains_exception_text(tmp_path):
    store = SiteCredentialStore(tmp_path / "private")
    with store.transaction("client") as transaction:
        transaction.save(SiteCredentialState.generate("client", 1000, 1000))
        transaction.record_failure(BootstrapFailureCode.PENDING_CHANGES)
    status = store.root / "client/.bootstrap-failure.json"
    assert status.stat().st_mode & 0o777 == 0o600
    assert json.loads(status.read_text()) == {"schema_version": 1, "site": "client", "code": "PENDING_CHANGES"}
    with pytest.raises(BootstrapError, match="PENDING_CHANGES"):
        SiteAutomationCredentialProvider().find_ready(store.root / "client/credentials.json", "client")


def test_downloader_does_not_sleep_or_open_http_after_fatal_bootstrap(tmp_path):
    store = SiteCredentialStore(tmp_path / "private")
    with store.transaction("client") as transaction:
        transaction.record_failure(BootstrapFailureCode.PENDING_CHANGES)
    def unexpected(*args):
        pytest.fail("Fatal bootstrap must not poll or open a network session")
    with pytest.raises(BootstrapError, match="PENDING_CHANGES"):
        LocalAgentDownloader(session_factory=unexpected, sleep=unexpected).download(
            "client", store.root / "client/credentials.json", 8080, tmp_path / "agents")


def test_reviewed_container_restart_can_clear_status_without_rotating_credentials(tmp_path):
    store = SiteCredentialStore(tmp_path / "private")
    state = replace(SiteCredentialState.generate("client", 1000, 1000), phase="accounts-ready",
                    bootstrap_password="", activation_complete=True)
    with store.transaction("client") as transaction:
        transaction.save(state)
        transaction.record_failure(BootstrapFailureCode.GENERIC)
    original = (store.root / "client/credentials.json").read_bytes()
    with store.transaction("client") as transaction:
        transaction.clear_failure()
        assert transaction.load_failure() is None
    assert (store.root / "client/credentials.json").read_bytes() == original


def test_unsafe_failure_status_is_rejected_not_repaired(tmp_path):
    store = SiteCredentialStore(tmp_path / "private")
    with store.transaction("client") as transaction:
        transaction.record_failure(BootstrapFailureCode.GENERIC)
    path = store.root / "client/.bootstrap-failure.json"
    path.chmod(0o644)
    with store.transaction("client") as transaction:
        with pytest.raises(BootstrapError):
            transaction.load_failure()
