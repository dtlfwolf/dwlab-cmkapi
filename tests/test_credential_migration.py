"""An existing site's old authentication must survive every failed migration."""

from dataclasses import replace
from types import SimpleNamespace
import tarfile

import pytest

from dwlabcmkapi.credential_bootstrap import BootstrapError, SiteCredentialStore
from dwlabcmkapi.credential_migration import ExistingSiteCredentialMigration, SiteMigrationBackup
from tests.test_account_bootstrap import FakeTransport
from tests.test_credential_bootstrap import FakeBackend, TestAuthorization


class MigrationTransport(FakeTransport):
    def __init__(self):
        from dwlabcmkapi.credential_bootstrap import SiteCredentialState
        super().__init__(replace(SiteCredentialState.generate("central", 6000, 6000),
                                 bootstrap_password="old-password"))


class Backup:
    def __init__(self, fails=False):
        self.calls = []
        self.fails = fails

    def create(self, site, path):
        self.calls.append((site, path))
        if self.fails:
            raise BootstrapError("backup failed")


def fixture(tmp_path, *, backup_fails=False):
    store = SiteCredentialStore(tmp_path / "private")
    backend = FakeBackend()
    backend.sites.add("central")
    transport = MigrationTransport()
    backup = Backup(backup_fails)
    migration = ExistingSiteCredentialMigration(
        store, backend, transport, backup, TestAuthorization(),
        identity_lookup=lambda _: SimpleNamespace(pw_uid=6000, pw_gid=6000),
    )
    return migration, store, backend, transport, backup


def test_explicit_approval_required_before_touching_state(tmp_path):
    migration, store, _, transport, backup = fixture(tmp_path)
    with pytest.raises(BootstrapError, match="approval"):
        migration.migrate("central", "old-password")
    assert not store.root.exists()
    assert not backup.calls
    assert not transport.calls


def test_successful_migration_backs_up_once_and_never_resets_old_password(tmp_path):
    migration, store, backend, transport, backup = fixture(tmp_path)
    result = migration.migrate("central", "old-password", approved=True)
    assert result.credential_gate_passed
    assert len(backup.calls) == 1
    assert not backend.passwords
    assert transport.users["cmkadmin"]["disabled"]
    with store.transaction("central") as transaction:
        state = transaction.load()
    assert state.legacy_migration
    assert state.bootstrap_password == ""
    assert state.automation_secret != state.emergency_password
    migration.migrate("central", "old-password", approved=True)
    assert len(backup.calls) == 1


def test_backup_failure_leaves_accounts_unchanged(tmp_path):
    migration, store, _, transport, backup = fixture(tmp_path, backup_fails=True)
    with pytest.raises(BootstrapError, match="backup"):
        migration.migrate("central", "old-password", approved=True)
    assert len(backup.calls) == 1
    assert not any(method != "GET" for _, method, _ in transport.calls)
    assert not transport.users["cmkadmin"]["disabled"]
    with store.transaction("central") as transaction:
        assert transaction.load() is None


def test_wrong_legacy_password_fails_before_backup_or_mutation(tmp_path):
    migration, _, _, transport, backup = fixture(tmp_path)
    with pytest.raises(BootstrapError):
        migration.migrate("central", "wrong-password", approved=True)
    assert not backup.calls
    assert not any(method != "GET" for _, method, _ in transport.calls)


def test_native_backup_is_private_and_does_not_follow_symlinks(tmp_path):
    sites = tmp_path / "sites"
    etc = sites / "central/etc"
    web = sites / "central/var/check_mk/web"
    etc.mkdir(parents=True)
    web.mkdir(parents=True)
    (etc / "users.mk").write_text("private-test-fixture")
    (etc / "external-link").symlink_to("/etc/shadow")
    destination = tmp_path / "backup.tar.gz"
    SiteMigrationBackup(sites).create("central", destination)
    assert destination.stat().st_mode & 0o777 == 0o600
    with tarfile.open(destination) as archive:
        assert archive.getmember("etc/external-link").issym()
    with pytest.raises(FileExistsError):
        SiteMigrationBackup(sites).create("central", destination)
