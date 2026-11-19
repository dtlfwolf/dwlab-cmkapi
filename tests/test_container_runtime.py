"""Legacy mountpoint repair is narrowly scoped and never recursive."""

from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dwlabcmkapi.container_runtime import ContainerRuntimePreparation
from dwlabcmkapi.credential_bootstrap import BootstrapError, RootBootstrapAuthorization, SiteCredentialState


class Backend:
    def __init__(self):
        self.calls = []
        self.stopped = True

    def is_stopped(self, site):
        return self.stopped

    def _run(self, arguments):
        self.calls.append(arguments)
        return SimpleNamespace(returncode=0)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(RootBootstrapAuthorization, "require_root", lambda *args: None)
    path = tmp_path / "client/tmp"
    path.mkdir(parents=True)
    state = replace(SiteCredentialState.generate("client", 1000, 1000), legacy_migration=True)
    backend = Backend()
    ownership = []
    service = ContainerRuntimePreparation(backend, tmp_path, lambda *args: ownership.append(args[1:]))
    monkeypatch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_uid=0, st_gid=0, st_mode=0o40755))
    return path, state, backend, ownership, service


def test_empty_recorded_legacy_mountpoint_is_repaired_and_native_skeleton_populated(runtime):
    path, state, backend, ownership, service = runtime
    service.prepare(state)
    assert ownership == [(1000, 1000)]
    assert path.stat().st_mode & 0o777 == 0o751
    assert backend.calls[0] == ["/usr/bin/omd", "config", "client", "set", "TMPFS", "off"]
    assert backend.calls[1][:3] == ["/usr/sbin/runuser", "--login", "client"]


def test_nonempty_root_owned_mountpoint_is_not_repaired(runtime):
    path, state, backend, ownership, service = runtime
    (path / "unexpected").write_text("preserve")
    with pytest.raises(BootstrapError, match="manual review"):
        service.prepare(state)
    assert not ownership and not backend.calls


def test_unapproved_root_mountpoint_is_not_adopted(runtime):
    _, state, backend, ownership, service = runtime
    with pytest.raises(BootstrapError, match="manual review"):
        service.prepare(replace(state, legacy_migration=False))
    assert not ownership and not backend.calls


def test_symlink_mountpoint_never_changes_external_ownership(runtime, tmp_path):
    path, state, backend, ownership, service = runtime
    path.rmdir()
    path.symlink_to(tmp_path)
    with pytest.raises(BootstrapError, match="unsafe"):
        service.prepare(state)
    assert not ownership and not backend.calls


def test_running_site_is_rejected_before_filesystem_changes(runtime):
    _, state, backend, ownership, service = runtime
    backend.stopped = False
    with pytest.raises(BootstrapError, match="stopped"):
        service.prepare(state)
    assert not ownership and not backend.calls


def test_foreign_directory_owner_is_not_changed(runtime, monkeypatch):
    _, state, backend, ownership, service = runtime
    monkeypatch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_uid=1234, st_gid=1234, st_mode=0o40755))
    with pytest.raises(BootstrapError, match="manual review"):
        service.prepare(state)
    assert not ownership and not backend.calls


def test_world_writable_site_owned_directory_is_rejected(runtime, monkeypatch):
    _, state, backend, ownership, service = runtime
    monkeypatch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_uid=1000, st_gid=1000, st_mode=0o40777))
    with pytest.raises(BootstrapError, match="World-writable"):
        service.prepare(state)
    assert not ownership and not backend.calls
