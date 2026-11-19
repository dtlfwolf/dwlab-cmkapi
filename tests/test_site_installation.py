"""Settings publication must not precede proven credential readiness."""

from dataclasses import replace

import pytest
import yaml

from dwlabcmkapi.credential_bootstrap import BootstrapError, SiteCredentialState, SiteCredentialStore
from dwlabcmkapi.site_installation import PrivateInstallationSettings
from tests.test_credential_bootstrap import TestAuthorization


def fixture(tmp_path, *, ready=True):
    path = tmp_path / "settings.yaml"
    path.write_text("cmkSite: central\ncmkadmin_password: private-test-fixture\ncmkVersion: 2.4.0p35\n")
    path.chmod(0o600)
    store = SiteCredentialStore(tmp_path / "private")
    state = SiteCredentialState.generate("central", 6000, 6000)
    if ready:
        state = replace(state, phase="accounts-ready", bootstrap_password="")
    with store.transaction("central") as transaction:
        transaction.save(state)
    settings = PrivateInstallationSettings(path, TestAuthorization())
    return path, store, settings


def test_publish_removes_old_password_and_preserves_other_settings(tmp_path):
    path, store, settings = fixture(tmp_path)
    data, raw = settings.read()
    settings.publish(data, raw, store, "central")
    updated = yaml.safe_load(path.read_text())
    assert "cmkadmin_password" not in updated
    assert updated["cmkCredentialsFile"] == str(store.root / "central/credentials.json")
    assert updated["cmkVersion"] == data["cmkVersion"]
    backup = store.root / "central/settings.before-bootstrap.yaml"
    assert backup.read_bytes() == raw
    assert backup.stat().st_mode & 0o777 == 0o600
    assert path.stat().st_mode & 0o777 == 0o600


def test_unready_state_never_publishes(tmp_path):
    path, store, settings = fixture(tmp_path, ready=False)
    data, raw = settings.read()
    with pytest.raises(BootstrapError, match="unverified"):
        settings.publish(data, raw, store, "central")
    assert path.read_bytes() == raw


def test_concurrent_yaml_change_is_not_overwritten(tmp_path):
    path, store, settings = fixture(tmp_path)
    data, raw = settings.read()
    path.write_text("cmkSite: changed-by-administrator\n")
    with pytest.raises(BootstrapError, match="concurrently"):
        settings.publish(data, raw, store, "central")
    assert "changed-by-administrator" in path.read_text()


def test_public_settings_rejected_without_repair(tmp_path):
    path, _, settings = fixture(tmp_path)
    path.chmod(0o644)
    with pytest.raises(BootstrapError, match="0600"):
        settings.read()
    assert path.stat().st_mode & 0o777 == 0o644


def test_symlinked_settings_rejected(tmp_path):
    path, _, _ = fixture(tmp_path)
    linked = path.with_name("link.yaml")
    linked.symlink_to(path)
    with pytest.raises(OSError):
        PrivateInstallationSettings(linked, TestAuthorization()).read()
