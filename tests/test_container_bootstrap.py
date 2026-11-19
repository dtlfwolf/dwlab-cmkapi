"""The container must not activate services until credential proofs pass."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from dwlabcmkapi import container_bootstrap as module
from dwlabcmkapi.credential_bootstrap import (
    BootstrapError, RootBootstrapAuthorization, SiteCredentialState, SiteCredentialStore,
)


class Backend:
    def __init__(self, exists=True):
        self.existing = exists
        self.calls = []

    def exists(self, site):
        return self.existing

    def _run(self, arguments):
        self.calls.append(arguments)
        return SimpleNamespace(returncode=0)


def test_completed_site_is_verified_before_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(RootBootstrapAuthorization, "require_root", lambda _: None)
    monkeypatch.setattr(module.os, "chown", lambda *args: None)
    store = SiteCredentialStore(tmp_path / "private")
    with store.transaction("client") as transaction:
        transaction.save(replace(SiteCredentialState.generate("client", 1000, 1000),
                                 phase="accounts-ready", bootstrap_password=""))
    backend = Backend()

    class Completion:
        def __init__(self, *args):
            pass

        def complete(self, site):
            assert site == "client"
            assert len(backend.calls) == 1
            backend.calls.append(["credentials-verified"])

    monkeypatch.setattr(module, "SiteAccountCompletion", Completion)
    root = tmp_path / "sites"
    (root / "client/etc/apache/conf.d").mkdir(parents=True)
    module.ContainerSiteBootstrap(store, backend, object(), root).configure("client")
    assert backend.calls[0] == ["/docker-entrypoint.sh", "/bin/true"]
    assert backend.calls[1] == ["credentials-verified"]
    assert backend.calls[-1][-2:] == ["AUTOSTART", "on"]
    assert "RedirectMatch ^/$ /client/" in (root / "client/etc/apache/conf.d/cmk_docker.conf").read_text()


def test_unowned_existing_site_never_invokes_vendor_entrypoint(tmp_path, monkeypatch):
    monkeypatch.setattr(RootBootstrapAuthorization, "require_root", lambda _: None)
    backend = Backend()
    with pytest.raises(BootstrapError, match="migration"):
        module.ContainerSiteBootstrap(SiteCredentialStore(tmp_path / "private"), backend).configure("client")
    assert not backend.calls


def test_verification_failure_prevents_service_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(RootBootstrapAuthorization, "require_root", lambda _: None)
    store = SiteCredentialStore(tmp_path / "private")
    with store.transaction("client") as transaction:
        transaction.save(replace(SiteCredentialState.generate("client", 1000, 1000),
                                 phase="accounts-ready", bootstrap_password=""))
    backend = Backend()

    class Completion:
        def __init__(self, *args):
            pass

        def complete(self, site):
            raise BootstrapError("verification failed")

    monkeypatch.setattr(module, "SiteAccountCompletion", Completion)
    with pytest.raises(BootstrapError, match="verification failed"):
        module.ContainerSiteBootstrap(store, backend).configure("client")
    assert backend.calls == [["/docker-entrypoint.sh", "/bin/true"]]
