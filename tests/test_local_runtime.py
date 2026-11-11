"""Exercise the site-user adapter without changing a real Checkmk instance."""

import json
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from dwlabcmkapi.local_runtime import LocalCheckmkRuntime
from dwlabcmkapi.reconciliation import ReconciliationError
from dwlabcmkapi.services import SiteConnectionState


class SiteRunner:
    def __init__(self):
        self.calls = []
        self.answers = []

    def __call__(self, command, **kwargs):
        assert command[:4] == ["runuser", "--login", "central", "--command"]
        assert kwargs["timeout"] > 0
        self.calls.append(shlex.split(command[4]))
        answer = self.answers.pop(0)
        return SimpleNamespace(returncode=0, stdout=answer, stderr="")


class TestLocalRuntime:
    def setup_method(self):
        self.runner = SiteRunner()
        self.runtime = LocalCheckmkRuntime("central", "/unused", True, runner=self.runner)

    def test_dns_lookup_filters_unusable_ipv4(self):
        self.runner.answers = ['["0.0.0.0", "127.0.0.1", "224.0.0.1", "10.8.0.2"]']
        assert self.runtime.resolve("client.vpn.test") == {"10.8.0.2"}
        assert self.runner.calls[0][-1] == "client.vpn.test"

    def test_cache_is_verified_not_just_refreshed(self):
        self.runner.answers = ["", '"10.8.0.99"']
        with pytest.raises(ReconciliationError, match="expected=10.8.0.2 actual=10.8.0.99"):
            self.runtime.refresh_dns("client.vpn.test", "10.8.0.2")
        assert self.runner.calls[0] == ["cmk", "--update-dns-cache"]

    @pytest.mark.parametrize("core,flag", [("nagios", "-R"), ("cmc", "-O")])
    def test_reload_uses_installed_core_type(self, core, flag):
        self.runner.answers = [core + "\n", ""]
        self.runtime.reload()
        assert self.runner.calls[-1] == ["cmk", flag]

    def test_activation_requires_explicit_opt_in(self):
        runtime = LocalCheckmkRuntime("central", "/unused", runner=self.runner)
        with pytest.raises(ReconciliationError, match="not enabled"):
            runtime.reload()
        assert not self.runner.calls

    def test_command_failure_is_actionable(self):
        runtime = LocalCheckmkRuntime("central", "/unused", runner=lambda *a, **kw:
            SimpleNamespace(returncode=1, stdout="", stderr="activation locked"))
        with pytest.raises(ReconciliationError, match="activation locked"):
            runtime.refresh_dns("client.vpn.test", "10.8.0.2")

    def test_core_address_comes_from_running_livestatus(self):
        self.runner.answers = ['[["10.8.0.2",0,1,42,"UP"]]']
        assert self.runtime.core_address("client.vpn.test") == "10.8.0.2"
        assert "GET hosts" in self.runner.calls[0][-1]
        assert "Filter: name = client.vpn.test" in self.runner.calls[0][-1]

    def test_input_cannot_inject_livestatus_query(self):
        with pytest.raises(ValueError):
            self.runtime.core_address("client\nCOMMAND malicious")

    def test_generated_scripts_compile_and_transport_matches_site_policy(self, monkeypatch):
        monkeypatch.setattr("dwlabcmkapi.local_runtime.time.time", lambda: 100)
        self.runner.answers = ["", json.dumps([["10.8.0.2", 0, 1, 100, "UP"]]), ""]
        self.runtime.verify("client.vpn.test", "10.8.0.2", SiteConnectionState(
            "client", True, connection_socket_type="tcp", connection_host="client.vpn.test",
            connection_port=6557, connection_encrypted=True, connection_verify=True))
        for command in self.runner.calls:
            compile(command[2], "site-script", "exec")
        probe = self.runner.calls[-1]
        assert probe[-5:] == ["client.vpn.test", "10.8.0.2", "6557", "True", "True"]
        assert "SCHEDULE_FORCED_HOST_CHECK" in self.runner.calls[0][-1]

    def test_wrong_address_cannot_pass_verification(self, monkeypatch):
        monkeypatch.setattr("dwlabcmkapi.local_runtime.time.time", lambda: 100)
        self.runner.answers = ["", json.dumps([["0.0.0.0", 0, 1, 100, "UP"]])]
        clock = iter([0, 999])
        self.runtime._clock = lambda: next(clock)
        with pytest.raises(ReconciliationError, match="Core verification failed"):
            self.runtime.verify("client.vpn.test", "10.8.0.2", SiteConnectionState(
                "client", True, connection_socket_type="tcp", connection_host="client.vpn.test"))

    def test_lookup_script_executes_in_a_real_python_process(self):
        def runner(command, **kwargs):
            return subprocess.run(shlex.split(command[-1]), **kwargs)

        runtime = LocalCheckmkRuntime("central", "/unused", runner=runner)
        assert runtime.resolve("127.0.0.1") == set()

    def test_site_lock_releases_after_failure(self, tmp_path):
        runtime = LocalCheckmkRuntime("central", tmp_path)
        with pytest.raises(RuntimeError):
            with runtime.lock():
                raise RuntimeError("test")
        with runtime.lock():
            assert (tmp_path / "central.lock").is_file()

    def test_two_workers_for_same_site_cannot_activate_concurrently(self, tmp_path):
        first = LocalCheckmkRuntime("central", tmp_path)
        second = LocalCheckmkRuntime("central", tmp_path)
        started, entered = Event(), Event()

        def worker():
            started.set()
            with second.lock():
                entered.set()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with first.lock():
                future = pool.submit(worker)
                assert started.wait(1)
                assert not entered.wait(0.05)
            future.result(timeout=1)
            assert entered.is_set()
