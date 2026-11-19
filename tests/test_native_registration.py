"""Native registration is explicit per supported Checkmk release line."""

import sys
import os
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from dwlabcmkapi.native_account_runner import NativeAccountRunner


def test_native_helper_rejects_another_os_identity_before_vendor_imports(monkeypatch):
    monkeypatch.setattr("dwlabcmkapi.native_account_runner.pwd.getpwnam",
                        lambda site: SimpleNamespace(pw_uid=os.geteuid() + 1, pw_gid=os.getegid()))
    with pytest.raises(ValueError, match="real site OS identity"):
        NativeAccountRunner().execute({"site": "example", "username": "cmkadmin",
            "password": "a" * 64, "method": "GET", "path": "/objects/user_config/dwlabcmkadm"})


@pytest.mark.parametrize("version,called,unused", [("2.4.0p35", "load_plugins", "register"),
                                                 ("2.5.0p11", "register", "load_plugins")])
def test_registration_uses_the_versioned_vendor_interface(monkeypatch, version, called, unused):
    monkeypatch.setattr("dwlabcmkapi.native_account_runner.pwd.getpwnam",
                        lambda site: SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid()))
    for name in ("cmk", "cmk.ccc", "cmk.ccc.version", "cmk.ccc.site", "cmk.utils",
                 "cmk.gui", "cmk.gui.wsgi", "cmk.gui.wsgi.app"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules["cmk.ccc"].version = SimpleNamespace(__version__=version)
    sys.modules["cmk.ccc.version"].edition = lambda root: "community"
    sys.modules["cmk.ccc.site"].omd_site = lambda: "example"
    sys.modules["cmk.utils"].paths = SimpleNamespace(omd_root="/omd")
    registration = SimpleNamespace(load_plugins=Mock(), register=Mock())
    sys.modules["cmk.gui"].main_modules = registration
    sys.modules["cmk.gui"].log = SimpleNamespace(init_logging=Mock())
    response = Mock(status_code=404, headers={})
    response.get_json.return_value = None
    app = Mock()
    app.test_client.return_value.__enter__ = Mock(return_value=app)
    app.test_client.return_value.__exit__ = Mock(return_value=False)
    app.open.return_value = response
    factory = Mock(return_value=app)
    sys.modules["cmk.gui.wsgi.app"].make_wsgi_app = factory
    result = NativeAccountRunner().execute({"site": "example", "username": "cmkadmin",
        "password": "a" * 64, "method": "GET", "path": "/objects/user_config/dwlabcmkadm"})
    assert result["status"] == 404
    getattr(registration, called).assert_called_once()
    getattr(registration, unused).assert_not_called()
    factory.assert_called_once_with("community")
    app.test_client.assert_called_once_with(use_cookies=False)
