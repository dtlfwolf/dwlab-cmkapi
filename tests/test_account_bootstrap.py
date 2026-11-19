"""Account bootstrap ordering, authentication proofs and crash-safe retirement."""

from dataclasses import replace
import io
import json
import logging
import os
from pathlib import Path
import subprocess

import pytest

from dwlabcmkapi.account_bootstrap import (
    NativeAccountTransport, SiteAccountCompletion,
)
from dwlabcmkapi.credential_bootstrap import (
    BootstrapError, NewSiteCredentialPreparation, SiteCredentialStore,
)
from dwlabcmkapi.native_account_runner import NativeAccountRunner
from dwlabcmkapi.automation_role import AutomationRoleProvisioner
from tests.test_credential_bootstrap import FakeBackend, TestAuthorization


class FakeTransport:
    def __init__(self, state):
        self.users = {"cmkadmin": self.user(state.bootstrap_password, "password")}
        self.calls = []
        self.fail_account = None
        self.fail_verification = None
        self.fail_retirement = False
        self.fail_after_retirement = False
        self.accept_old_password = False
        self.etag = '"verified-etag"'
        self.role = None

    def user(self, secret, auth_type):
        return {"secret": secret, "roles": ["admin"], "disabled": False,
                "auth_type": auth_type, "store_secret": False}

    def verify_site(self, state):
        pass

    def request(self, state, username, password, method, path, *, body=None, etag=None):
        self.calls.append((username, method, path))
        actor = self.users.get(username)
        if username == "cmkadmin" and self.accept_old_password:
            pass
        elif (actor is None or actor["secret"] != password or actor["disabled"]
              or self.fail_verification == username):
            return {"status": 401}
        if username == "dwlab-automation":
            return {"status": 200 if path == "/version" else 403}
        if "/user_role/" in path:
            if method == "POST":
                self.role = {"id": AutomationRoleProvisioner.NAME, "builtin": False,
                             "basedon": "user", "permissions": list(AutomationRoleProvisioner.ALLOWED | {"wato.users"}),
                             "available_permissions": list(AutomationRoleProvisioner.ALLOWED | {"wato.users"})}
            elif method == "PUT":
                self.role["permissions"] = [key for key, value in body["new_permissions"].items() if value == "yes"]
            return {"status": 200, "role": self.role} if self.role else {"status": 404}
        account = path.rsplit("/", 1)[-1]
        if method == "GET":
            if account not in self.users:
                return {"status": 404}
            return {"status": 200, "etag": self.etag,
                    "user": {"id": account, **{key: value for key, value in self.users[account].items()
                                              if key != "secret"}}}
        if method == "POST":
            account = body["username"]
            if account == self.fail_account:
                return {"status": 400}
            if account in self.users:
                return {"status": 409}
            auth = body["auth_option"]
            self.users[account] = self.user(auth.get("password", auth.get("secret")), auth["auth_type"])
            self.users[account]["roles"] = body["roles"]
            return {"status": 200}
        if method == "PUT":
            assert username == "dwlabcmkadm"
            assert body == {"disable_login": True, "auth_option": {"auth_type": "remove"}}
            assert etag == self.etag
            if self.fail_retirement:
                return {"status": 500}
            self.users[account].update(disabled=True, secret=None)
            if self.fail_after_retirement:
                raise BootstrapError("Interrupted after disabling bootstrap")
            return {"status": 200}
        raise AssertionError("Unexpected operation")


class TestAccountCompletion:
    def fixture(self, tmp_path):
        store = SiteCredentialStore(tmp_path / "private")
        NewSiteCredentialPreparation(store, FakeBackend(), TestAuthorization()).prepare("central", 6000, 6000)
        with store.transaction("central") as transaction:
            state = transaction.load()
        transport = FakeTransport(state)
        completion = SiteAccountCompletion(store, transport, TestAuthorization())
        return store, state, transport, completion

    def test_verified_accounts_precede_retirement_and_secret_removal(self, tmp_path, caplog):
        store, original, transport, completion = self.fixture(tmp_path)
        with caplog.at_level(logging.INFO):
            result = completion.complete("central")
        assert result.credential_gate_passed
        assert not result.activation_performed
        assert result.phase == "accounts-ready"
        content = (store.root / "central/credentials.json").read_text()
        assert "bootstrap_password" not in json.loads(content)
        assert original.bootstrap_password not in content
        with store.transaction("central") as transaction:
            state = transaction.load()
        assert state.bootstrap_password == ""
        assert state.emergency_password == original.emergency_password
        assert state.automation_secret == original.automation_secret
        assert transport.users["cmkadmin"]["disabled"]
        retirement = next(i for i, call in enumerate(transport.calls)
                          if call[1:] == ("PUT", "/objects/user_config/cmkadmin"))
        assert ("dwlabcmkadm", "GET", "/objects/user_config/dwlabcmkadm") in transport.calls[:retirement]
        assert ("dwlab-automation", "GET", "/version") in transport.calls[:retirement]
        for secret in (original.bootstrap_password, original.emergency_password, original.automation_secret):
            assert secret not in caplog.text
            assert secret not in repr(result)

    @pytest.mark.parametrize("failure", ["create", "verify", "etag", "retire", "old-accepted"])
    def test_failures_never_clear_recovery_material(self, tmp_path, failure):
        store, state, transport, completion = self.fixture(tmp_path)
        if failure == "create":
            transport.fail_account = "dwlab-automation"
        elif failure == "verify":
            transport.fail_verification = "dwlabcmkadm"
        elif failure == "etag":
            transport.etag = None
        elif failure == "retire":
            transport.fail_retirement = True
        else:
            transport.accept_old_password = True
        with pytest.raises(BootstrapError, match="activation blocked"):
            completion.complete("central")
        with store.transaction("central") as transaction:
            after = transaction.load()
        assert after.bootstrap_password == state.bootstrap_password
        assert after.phase != "accounts-ready"
        if failure in {"create", "verify", "etag"}:
            assert not transport.users["cmkadmin"]["disabled"]
            assert not any(call[1:] == ("PUT", "/objects/user_config/cmkadmin") for call in transport.calls)

    def test_preexisting_user_is_not_overwritten(self, tmp_path):
        store, _, transport, completion = self.fixture(tmp_path)
        transport.users["dwlabcmkadm"] = transport.user("unrelated", "password")
        with pytest.raises(BootstrapError):
            completion.complete("central")
        assert transport.users["dwlabcmkadm"]["secret"] == "unrelated"
        assert not any(call[1] in {"POST", "PUT"} for call in transport.calls)
        with store.transaction("central") as transaction:
            assert transaction.load().phase == "awaiting-accounts"

    def test_retry_after_partial_creation_does_not_reset_accounts(self, tmp_path):
        _, state, transport, completion = self.fixture(tmp_path)
        transport.fail_account = "dwlab-automation"
        with pytest.raises(BootstrapError):
            completion.complete("central")
        transport.fail_account = None
        completion.complete("central")
        assert transport.users["dwlabcmkadm"]["secret"] == state.emergency_password
        assert sum(call[1] == "POST" and "/user_config/" in call[2] for call in transport.calls) == 3

    def test_retry_after_bootstrap_was_disabled(self, tmp_path):
        store, _, transport, completion = self.fixture(tmp_path)
        transport.fail_after_retirement = True
        with pytest.raises(BootstrapError):
            completion.complete("central")
        with store.transaction("central") as transaction:
            assert transaction.load().phase == "retiring-bootstrap"
        transport.fail_after_retirement = False
        completion.complete("central")
        assert sum(call[1:] == ("PUT", "/objects/user_config/cmkadmin") for call in transport.calls) == 1

    def test_completed_retry_is_read_only(self, tmp_path):
        store, _, transport, completion = self.fixture(tmp_path)
        first = completion.complete("central")
        transport.calls.clear()
        second = completion.complete("central")
        assert first == second
        assert all(call[1] == "GET" for call in transport.calls)
        assert "bootstrap_password" not in json.loads((store.root / "central/credentials.json").read_text())

    def test_default_denial_does_not_touch_store_or_transport(self, tmp_path, monkeypatch):
        monkeypatch.setattr(os, "geteuid", lambda: 1001)
        store = SiteCredentialStore(tmp_path / "private")
        with pytest.raises(BootstrapError):
            SiteAccountCompletion(store, None).complete("central")
        assert not store.root.exists()

    def test_changed_existing_account_is_not_repaired_on_retry(self, tmp_path):
        _, _, transport, completion = self.fixture(tmp_path)
        transport.fail_account = "dwlab-automation"
        with pytest.raises(BootstrapError):
            completion.complete("central")
        transport.users["dwlabcmkadm"]["secret"] = "changed-outside-workflow"
        transport.fail_account = None
        with pytest.raises(BootstrapError):
            completion.complete("central")
        assert transport.users["dwlabcmkadm"]["secret"] == "changed-outside-workflow"
        assert not transport.users["cmkadmin"]["disabled"]

    @pytest.mark.parametrize("field,value", [
        ("roles", ["user"]), ("disabled", True), ("auth_type", "automation"),
    ])
    def test_wrong_administrator_attributes_block_retirement(self, tmp_path, field, value):
        store, state, transport, completion = self.fixture(tmp_path)
        with store.transaction("central") as transaction:
            transaction.save(replace(state, phase="provisioning-accounts"))
        transport.users["dwlabcmkadm"] = transport.user(state.emergency_password, "password")
        transport.users["dwlabcmkadm"][field] = value
        with pytest.raises(BootstrapError):
            completion.complete("central")
        assert not any(call[1:] == ("PUT", "/objects/user_config/cmkadmin") for call in transport.calls)
        assert not transport.users["cmkadmin"]["disabled"]


class TestNativeTransport:
    def test_secrets_only_travel_on_stdin(self, tmp_path):
        _, state, _, _ = TestAccountCompletion().fixture(tmp_path)
        calls = []

        def runner(command, **options):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, b'{"status":200}')

        transport = NativeAccountTransport(runner, TestAuthorization())
        transport.request(state, "cmkadmin", state.bootstrap_password, "POST",
                          "/domain-types/user_config/collections/all",
                          body={"password": state.emergency_password})
        command, options = calls[0]
        for secret in (state.bootstrap_password, state.emergency_password):
            assert secret not in repr(command)
            assert secret not in repr(options["env"])
            assert secret.encode() in options["input"]
        assert options["stderr"] == subprocess.DEVNULL

    def test_native_error_payload_is_not_echoed(self, tmp_path):
        _, state, _, _ = TestAccountCompletion().fixture(tmp_path)
        transport = NativeAccountTransport(
            lambda cmd, **opts: subprocess.CompletedProcess(cmd, 1, state.bootstrap_password.encode()),
            TestAuthorization(),
        )
        with pytest.raises(BootstrapError) as error:
            transport.request(state, "cmkadmin", state.bootstrap_password, "GET", "/objects/user_config/cmkadmin")
        assert state.bootstrap_password not in str(error.value)

    def test_helper_failure_is_nonsecret(self, monkeypatch, capsys):
        secret = "secret-that-must-not-appear"
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))

        def fail(self, request):
            raise ValueError(secret)

        monkeypatch.setattr(NativeAccountRunner, "execute", fail)
        assert NativeAccountRunner().run() == 1
        captured = capsys.readouterr()
        assert secret not in captured.out + captured.err
        assert "Traceback" not in captured.out + captured.err

    def test_helper_rejects_unknown_route_before_native_imports(self):
        with pytest.raises(ValueError, match="Unsupported account operation"):
            NativeAccountRunner().execute({
                "site": "central", "method": "POST", "path": "/unrelated-operation",
                "username": "cmkadmin", "password": "a" * 64,
            })
