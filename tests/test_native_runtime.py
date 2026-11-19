"""The native temporary-skeleton adapter is explicitly versioned."""

import os
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from dwlabcmkapi.native_runtime_runner import NativeRuntimeRunner


@pytest.mark.parametrize("version", ["2.4.0p35", "2.5.0p11"])
def test_vendor_initializer_matches_the_supported_release_contract(monkeypatch, version):
    monkeypatch.setattr("dwlabcmkapi.native_runtime_runner.pwd.getpwnam",
                        lambda site: SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid()))
    for name in ("cmk", "cmk.ccc", "cmk.ccc.site", "omdlib", "omdlib.contexts",
                 "omdlib.main", "omdlib.tmpfs", "omdlib.version_info"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules["cmk.ccc"].version = SimpleNamespace(__version__=version)
    sys.modules["cmk.ccc.site"].omd_site = lambda: "example"
    sys.modules["omdlib"].__version__ = "native"
    context = SimpleNamespace(conf={"TMPFS": "off"}, set_config=Mock(),
                              is_stopped=lambda verbose: True, tmp_dir="/omd/sites/example/tmp",
                              replacements=lambda: {"site": "example"}, skel_permissions="permissions")
    sys.modules["omdlib.contexts"].SiteContext = lambda site: context
    sys.modules["omdlib.main"].read_site_config = lambda home: context.conf
    sys.modules["omdlib.version_info"].VersionInfo = lambda: "version-info"
    prepare = Mock()
    sys.modules["omdlib.tmpfs"].prepare_and_populate_tmpfs = prepare
    NativeRuntimeRunner().prepare("example")
    if version.startswith("2.4."):
        prepare.assert_called_once_with("version-info", context, "/omd/versions/native/skel")
    else:
        prepare.assert_called_once_with(context.conf, "version-info", "example", "/omd/sites/example",
                                        context.tmp_dir, {"site": "example"}, "permissions",
                                        "/omd/versions/native/skel")
