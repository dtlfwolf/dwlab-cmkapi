"""Stopped-site preparation, secret isolation and fail-closed recovery."""

from concurrent.futures import ThreadPoolExecutor
import logging
import os
from pathlib import Path
import stat
import subprocess

import pytest

from dwlabcmkapi.credential_bootstrap import (
    BootstrapCli, BootstrapError, NewSiteCredentialPreparation,
    OmdBootstrapBackend, RootBootstrapAuthorization, SiteCredentialStore,
)


class TestAuthorization:
    __test__ = False

    def require_root(self):
        pass


class FakeBackend:
    def __init__(self):
        self.sites = set()
        self.calls = []
        self.passwords = {}
        self.stopped = True
        self.fail_create = False
        self.fail_password = False

    def verify_support(self):
        self.calls.append("support")

    def exists(self, site):
        return site in self.sites

    def create(self, site, uid, gid):
        self.calls.append("create")
        if self.fail_create:
            raise BootstrapError("Creation failed")
        self.sites.add(site)

    def is_stopped(self, site):
        return self.stopped

    def set_bootstrap_password(self, site, password):
        self.calls.append("password")
        if self.fail_password:
            raise BootstrapError("Password setup failed")
        self.passwords[site] = password


class TestCredentialPreparation:
    def service(self, tmp_path):
        store = SiteCredentialStore(tmp_path / "private")
        backend = FakeBackend()
        return NewSiteCredentialPreparation(store, backend, TestAuthorization()), store, backend

    def test_unique_private_credentials_and_nonsecret_result(self, tmp_path, caplog):
        service, store, backend = self.service(tmp_path)
        with caplog.at_level(logging.INFO):
            result = service.prepare("central", 6000, 6000)
        assert result.phase == "awaiting-accounts"
        assert not result.activation_allowed
        with store.transaction("central") as transaction:
            state = transaction.load()
        values = {state.bootstrap_password, state.emergency_password, state.automation_secret}
        assert len(values) == 3
        assert backend.passwords["central"] == state.bootstrap_password
        for value in values:
            assert len(value) == 64
            assert value not in repr(state)
            assert value not in repr(result)
            assert value not in caplog.text
        assert backend.calls == ["support", "create", "password"]
        assert f"caller_uid={os.geteuid()}" in caplog.text
        for path in (store.root, store.root / "central"):
            assert stat.S_IMODE(path.stat().st_mode) == 0o700
        assert stat.S_IMODE(Path(result.credential_file).stat().st_mode) == 0o600
        assert set(path.name for path in (store.root / "central").iterdir()) == {
            ".lock", "credentials.json",
        }

    def test_retries_do_not_rotate_or_recreate(self, tmp_path):
        service, store, backend = self.service(tmp_path)
        first = service.prepare("central", 6000, 6000)
        before = Path(first.credential_file).read_bytes()
        second = service.prepare("central", 6000, 6000)
        assert second == first
        assert Path(first.credential_file).read_bytes() == before
        assert backend.calls.count("create") == 1
        assert backend.calls.count("password") == 1

    def test_sites_do_not_share_credentials(self, tmp_path):
        service, store, _ = self.service(tmp_path)
        service.prepare("central", 6000, 6000)
        service.prepare("client1", 6001, 6001)
        with store.transaction("central") as transaction:
            first = transaction.load()
        with store.transaction("client1") as transaction:
            second = transaction.load()
        assert set((first.bootstrap_password, first.emergency_password, first.automation_secret)).isdisjoint(
            (second.bootstrap_password, second.emergency_password, second.automation_secret)
        )

    def test_existing_site_is_never_adopted(self, tmp_path):
        service, store, backend = self.service(tmp_path)
        backend.sites.add("central")
        with pytest.raises(BootstrapError, match="Existing site"):
            service.prepare("central", 6000, 6000)
        assert backend.calls == ["support"]
        assert not (store.root / "central/credentials.json").exists()

    def test_interrupted_creation_requires_review(self, tmp_path):
        service, store, backend = self.service(tmp_path)
        backend.fail_create = True
        with pytest.raises(BootstrapError, match="Creation failed"):
            service.prepare("central", 6000, 6000)
        before = (store.root / "central/credentials.json").read_bytes()
        backend.fail_create = False
        with pytest.raises(BootstrapError, match="Interrupted"):
            service.prepare("central", 6000, 6000)
        assert (store.root / "central/credentials.json").read_bytes() == before
        assert backend.calls.count("create") == 1

    def test_password_failure_can_resume_without_new_secrets(self, tmp_path):
        service, store, backend = self.service(tmp_path)
        backend.fail_password = True
        with pytest.raises(BootstrapError, match="Password setup failed"):
            service.prepare("central", 6000, 6000)
        with store.transaction("central") as transaction:
            first = transaction.load()
        assert first.phase == "created"
        backend.fail_password = False
        result = service.prepare("central", 6000, 6000)
        with store.transaction("central") as transaction:
            after = transaction.load()
        assert after.bootstrap_password == first.bootstrap_password
        assert result.phase == "awaiting-accounts"
        assert backend.calls.count("create") == 1

    @pytest.mark.parametrize("problem", ["running", "missing", "changed-uid"])
    def test_unexpected_site_state_fails_closed(self, tmp_path, problem):
        service, _, backend = self.service(tmp_path)
        service.prepare("central", 6000, 6000)
        if problem == "running":
            backend.stopped = False
        if problem == "missing":
            backend.sites.clear()
        with pytest.raises(BootstrapError):
            service.prepare("central", 6001 if problem == "changed-uid" else 6000, 6000)
        assert backend.calls.count("password") == 1

    def test_default_authorization_precedes_state_creation(self, tmp_path, monkeypatch):
        monkeypatch.setattr(os, "geteuid", lambda: 1001)
        store = SiteCredentialStore(tmp_path / "private")
        backend = FakeBackend()
        with pytest.raises(BootstrapError, match="root"):
            NewSiteCredentialPreparation(store, backend).prepare("central", 6000, 6000)
        assert not store.root.exists()
        assert not backend.calls

    @pytest.mark.parametrize("site", ["../central", "/root", "-option", "central;false"])
    def test_site_names_cannot_escape_store(self, tmp_path, site):
        service, store, _ = self.service(tmp_path)
        with pytest.raises(BootstrapError, match="site name"):
            service.prepare(site, 6000, 6000)
        assert not store.root.exists()

    def test_concurrent_preparation_creates_only_once(self, tmp_path):
        service, _, backend = self.service(tmp_path)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: service.prepare("central", 6000, 6000), range(2)))
        assert results[0] == results[1]
        assert backend.calls.count("create") == 1
        assert backend.calls.count("password") == 1


class TestPrivateStore:
    def initialized(self, tmp_path):
        service, store, _ = TestCredentialPreparation().service(tmp_path)
        service.prepare("central", 6000, 6000)
        return store, store.root / "central/credentials.json"

    @pytest.mark.parametrize("target", ["file", "directory", "lock"])
    def test_symlinks_are_rejected(self, tmp_path, target):
        store, path = self.initialized(tmp_path)
        if target == "directory":
            path = store.root / "central"
        elif target == "lock":
            path = store.root / "central/.lock"
        saved = path.with_name(path.name + "-original")
        path.rename(saved)
        path.symlink_to(saved)
        with pytest.raises((OSError, BootstrapError)):
            with store.transaction("central") as transaction:
                transaction.load()
        assert path.is_symlink()

    def test_hardlinked_credential_file_is_rejected(self, tmp_path):
        store, path = self.initialized(tmp_path)
        os.link(path, path.with_name("shared"))
        with pytest.raises(BootstrapError, match="singly linked"):
            with store.transaction("central") as transaction:
                transaction.load()

    @pytest.mark.parametrize("target", ["file", "directory"])
    def test_public_modes_are_not_repaired(self, tmp_path, target):
        store, path = self.initialized(tmp_path)
        if target == "directory":
            path = store.root / "central"
        mode = 0o755 if target == "directory" else 0o644
        path.chmod(mode)
        with pytest.raises(BootstrapError):
            with store.transaction("central") as transaction:
                transaction.load()
        assert stat.S_IMODE(path.stat().st_mode) == mode

    def test_invalid_json_is_not_echoed_or_overwritten(self, tmp_path):
        store, path = self.initialized(tmp_path)
        path.write_text("confidential-malformed-content")
        with pytest.raises(BootstrapError) as error:
            with store.transaction("central") as transaction:
                transaction.load()
        assert "confidential" not in str(error.value)
        assert path.read_text() == "confidential-malformed-content"


class TestNativeAdapter:
    def test_root_authorization_ignores_forged_environment_identity(self, monkeypatch):
        monkeypatch.setattr(os, "geteuid", lambda: 1001)
        monkeypatch.setenv("SUDO_UID", "0")
        monkeypatch.setenv("USER", "root")
        with pytest.raises(BootstrapError, match="root"):
            RootBootstrapAuthorization().require_root()

    def test_secrets_use_stdin_not_arguments_environment_or_output(self):
        calls = []

        def runner(command, **options):
            calls.append((command, options))
            if command[-1] == "version":
                return subprocess.CompletedProcess(command, 0, b"OMD - Version 2.4.0p35.cre")
            return subprocess.CompletedProcess(command, 0)

        backend = OmdBootstrapBackend(runner=runner, authorization=TestAuthorization())
        backend.verify_support()
        backend.create("central", 6000, 6000)
        backend.set_bootstrap_password("central", "never-echo-this")
        assert "--no-autostart" in calls[1][0]
        for command, options in calls:
            assert "never-echo-this" not in repr(command)
            assert "never-echo-this" not in repr(options["env"])
            assert options["stderr"] == subprocess.DEVNULL
        assert calls[1][1]["stdout"] == subprocess.DEVNULL
        assert calls[2][1]["stdout"] == subprocess.DEVNULL
        assert calls[2][1]["input"] == b"never-echo-this\n"
        assert calls[2][0][-1] == "cmk-passwd --stdin cmkadmin"

    @pytest.mark.parametrize("version", [b"2.3.0p1", b"3.0.0p1", b"garbled"])
    def test_unsupported_versions_are_rejected(self, version):
        backend = OmdBootstrapBackend(
            runner=lambda cmd, **opts: subprocess.CompletedProcess(cmd, 0, b"OMD - Version " + version),
            authorization=TestAuthorization(),
        )
        with pytest.raises(BootstrapError, match="supports"):
            backend.verify_support()

    def test_checkmk_25_version_is_accepted(self):
        backend = OmdBootstrapBackend(
            runner=lambda cmd, **opts: subprocess.CompletedProcess(
                cmd, 0, b"OMD - Open Monitoring Distribution Version 2.5.0p11.community"
            ), authorization=TestAuthorization(),
        )
        backend.verify_support()

    def test_native_failure_does_not_echo_sensitive_diagnostics(self):
        def runner(command, **options):
            raise subprocess.CalledProcessError(1, command, output=b"secret-output")

        backend = OmdBootstrapBackend(runner=runner, authorization=TestAuthorization())
        with pytest.raises(BootstrapError) as error:
            backend.set_bootstrap_password("central", "secret-input")
        assert "secret" not in str(error.value)

    def test_cli_denial_is_readable_and_nonsecret(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(os, "geteuid", lambda: 1001)
        result = BootstrapCli().run([
            "prepare-new-site", "--site", "central", "--site-uid", "6000",
            "--site-gid", "6000", "--credential-root", str(tmp_path / "private"),
        ])
        captured = capsys.readouterr()
        assert result == 1
        assert "root privileges" in captured.err
        assert "STEP FAIL" in captured.err
        assert "Traceback" not in captured.err
        assert not captured.out
