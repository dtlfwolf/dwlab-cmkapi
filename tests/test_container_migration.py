"""Preserve legacy Docker credentials privately before any destructive upgrade."""

import json
import subprocess

import pytest

from dwlabcmkapi.container_migration import LegacyContainerMigration
from dwlabcmkapi.credential_bootstrap import BootstrapError, BootstrapFailureCode, RootBootstrapAuthorization, SiteCredentialStore


class Docker:
    def __init__(self, fail_backup=False, pending=False, denied=False):
        self.calls = []
        self.fail_backup = fail_backup
        self.pending, self.denied = pending, denied

    def __call__(self, arguments, **options):
        self.calls.append((arguments, options))
        assert arguments[:3] == ["docker", "--host", "unix:///var/run/docker.sock"]
        assert "DOCKER_HOST" not in options["env"]
        assert "private-legacy-secret" not in repr(arguments) + repr(options["env"])
        if arguments[3] == "inspect":
            content = json.dumps([{"Config": {"Env": ["CMK_SITE_ID=client", "CMK_PASSWORD=private-legacy-secret"]}}]).encode()
        elif "/usr/sbin/runuser" in arguments:
            request = json.loads(options["input"])
            assert request["method"] == "GET"
            assert request["password"] == "private-legacy-secret"
            status = 401 if self.denied else 404
            data = {"status": status}
            if "pending_changes" in request["path"]:
                changes = [{"id": "fixture", "action_name": "create-host", "user_id": "cmkadmin"}] if self.pending else []
                data = {"status": 200, "pending_changes": changes}
            elif "site_connection" in request["path"]:
                data = {"status": 200, "site_connections": [{"id": "client", "replication_enabled": False}]}
            content = json.dumps(data).encode()
        elif "id" in arguments:
            content = b"1000\n"
        elif "tar" in arguments:
            if self.fail_backup:
                return subprocess.CompletedProcess(arguments, 1)
            options["stdout"].write(b"private recovery fixture")
            content = b""
        else:
            content = b""
        return subprocess.CompletedProcess(arguments, 0, stdout=content)


@pytest.fixture(autouse=True)
def authorization(monkeypatch):
    monkeypatch.setattr(RootBootstrapAuthorization, "require_root", lambda _: None)


def test_explicit_approval_before_docker_or_state_access(tmp_path):
    docker = Docker()
    store = SiteCredentialStore(tmp_path / "private")
    with pytest.raises(BootstrapError, match="approval"):
        LegacyContainerMigration(store, docker).prepare("client")
    assert not docker.calls
    assert not store.root.exists()


def test_prepare_preserves_secret_and_backup_but_does_not_retire_accounts(tmp_path):
    docker = Docker()
    store = SiteCredentialStore(tmp_path / "private")
    migration = LegacyContainerMigration(store, docker)
    migration.prepare("client", approved=True)
    migration.check("client")
    with store.transaction("client") as transaction:
        state = transaction.load()
    assert state.legacy_migration
    assert state.phase == "awaiting-accounts"
    assert state.bootstrap_password == "private-legacy-secret"
    assert (store.root / "client/before-migration.tar.gz").stat().st_mode & 0o777 == 0o600
    assert not any("rm" in arguments for arguments, _ in docker.calls)


def test_backup_failure_never_marks_migration_ready(tmp_path):
    store = SiteCredentialStore(tmp_path / "private")
    migration = LegacyContainerMigration(store, Docker(fail_backup=True))
    with pytest.raises(BootstrapError):
        migration.prepare("client", approved=True)
    with store.transaction("client") as transaction:
        assert transaction.load() is None
    with pytest.raises(BootstrapError):
        migration.check("client")


def test_guard_refuses_unprepared_existing_container(tmp_path):
    docker = Docker()
    migration = LegacyContainerMigration(SiteCredentialStore(tmp_path / "private"), docker)
    with pytest.raises(BootstrapError, match="before replacing"):
        migration.check("client")
    assert not docker.calls


def test_invalid_site_does_not_reach_docker(tmp_path):
    docker = Docker()
    migration = LegacyContainerMigration(SiteCredentialStore(tmp_path / "private"), docker)
    with pytest.raises(BootstrapError):
        migration.prepare("../escape", approved=True)
    assert not docker.calls


@pytest.mark.parametrize("argument,code", [("pending", BootstrapFailureCode.PENDING_CHANGES),
                                          ("denied", BootstrapFailureCode.NATIVE_OPERATION)])
def test_preflight_blocks_before_stop_backup_or_state_publication(tmp_path, argument, code):
    docker = Docker(**{argument: True})
    store = SiteCredentialStore(tmp_path / "private")
    with pytest.raises(BootstrapError) as error:
        LegacyContainerMigration(store, docker).prepare("client", approved=True)
    assert error.value.code is code
    assert not any("stop" in args or "tar" in args or "rm" in args for args, _ in docker.calls)
    assert not (store.root / "client/credentials.json").exists()
    assert not (store.root / "client/before-migration.tar.gz").exists()


def test_docker_preflight_rejects_mutations_before_execution(tmp_path):
    from dwlabcmkapi.container_migration import DockerReadOnlyAccountInspection
    from dwlabcmkapi.credential_bootstrap import SiteCredentialState
    docker = Docker()
    adapter = DockerReadOnlyAccountInspection("client", docker)
    state = SiteCredentialState.generate("client", 1000, 1000)
    with pytest.raises(BootstrapError, match="only"):
        adapter.request(state, "cmkadmin", "private-legacy-secret", "POST",
                        "/domain-types/activation_run/actions/activate-changes/invoke")
    assert not docker.calls
