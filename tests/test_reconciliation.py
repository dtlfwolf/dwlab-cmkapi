"""VPN reconnects must repair effective core state, not just catalog objects."""

from contextlib import contextmanager

import pytest

from dwlabcmkapi.catalog_queue import CatalogQueueWorker, CatalogRequestStore
from dwlabcmkapi.reconciliation import (
    ClientReconciliationService, ReconciliationError, SupersededCatalogRequest,
)
from dwlabcmkapi.services import ClientCatalogService
from test_domain_services import FakeGateway, _central_server, _client_instance


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Runtime:
    def __init__(self, address="10.8.0.2", core="10.8.0.2"):
        self.address, self.core = address, core
        self.calls = []
        self.locked = False
        self.failure = None

    @contextmanager
    def lock(self):
        assert not self.locked
        self.locked = True
        try:
            yield
        finally:
            self.locked = False

    def resolve(self, hostname):
        assert self.locked
        self.calls.append("dns")
        return {self.address} if self.address else set()

    def refresh_dns(self, hostname, address):
        assert self.locked
        self.calls.append("cache")

    def core_address(self, hostname):
        return self.core

    def reload(self):
        assert self.locked
        self.calls.append("reload")
        if self.failure:
            raise self.failure
        self.core = self.address

    def verify(self, hostname, address, connection):
        assert self.locked
        assert self.core == address
        self.calls.append("verify")


class TestClientReconciliation:
    def setup_method(self):
        self.clock = Clock()
        self.gateway = FakeGateway(True, True, True)
        self.runtime = Runtime()

    def service(self):
        return ClientReconciliationService(
            ClientCatalogService(self.gateway), self.runtime, timeout=3,
            monotonic=self.clock.monotonic, sleep=self.clock.sleep)

    def reconcile(self, expected="10.8.0.2", current=lambda: True):
        return self.service().reconcile(_central_server(), _client_instance(), expected, current)

    def test_unchanged_reconnect_verifies_without_reloading(self, caplog):
        with caplog.at_level("INFO"):
            self.reconcile()
        assert "reload" not in self.runtime.calls
        assert "verify" in self.runtime.calls
        assert "MILESTONE PASS: cmk-reconcile/runtime" in caplog.text
        assert ("activate_changes",) not in self.gateway.calls

    @pytest.mark.parametrize("old", ["0.0.0.0", "10.8.0.99", ""])
    def test_repairs_stale_or_invalid_running_core_address(self, old):
        self.runtime.core = old
        self.reconcile()
        assert self.runtime.calls.count("reload") == 1
        assert self.runtime.calls.index("cache") < self.runtime.calls.index("reload")

    def test_new_host_is_created_before_cache_refresh_and_discovery_after_reload(self):
        self.gateway = FakeGateway(False, False, False)
        self.runtime.core = ""
        original = self.runtime.refresh_dns

        def refresh(host, address):
            assert self.gateway.host_exists
            assert not any(c[0] == "run_discovery" for c in self.gateway.calls)
            original(host, address)

        self.runtime.refresh_dns = refresh
        result = self.reconcile()
        assert result.host_created
        assert self.runtime.calls.count("reload") == 1
        assert self.gateway.calls.count(("activate_and_wait", "central")) == 2
        assert any(c[0] == "run_discovery" for c in self.gateway.calls)
        assert ("create_host", "client01.vpn.dwlab", "/", "") in self.gateway.calls

    def test_delayed_dns_is_retried_until_it_matches_the_event(self):
        original = self.runtime.resolve

        def resolve(host):
            self.runtime.address = "10.8.0.99" if self.clock.now < 2 else "10.8.0.2"
            return original(host)

        self.runtime.resolve = resolve
        self.reconcile()
        assert self.clock.now == 2

    @pytest.mark.parametrize("actual", ["", "10.8.0.99"])
    def test_dns_timeout_reports_expected_and_actual_without_mutation(self, actual, caplog):
        self.runtime.address = actual
        with pytest.raises(ReconciliationError, match="expected=10.8.0.2 actual="):
            self.reconcile()
        assert "cache" not in self.runtime.calls
        assert not self.gateway.calls
        assert "MILESTONE FAIL: cmk-reconcile/dns" in caplog.text

    def test_failed_activation_is_not_reported_as_registered(self, caplog):
        self.runtime.core = "0.0.0.0"
        self.runtime.failure = ReconciliationError("core reload failed")
        with pytest.raises(ReconciliationError, match="core reload failed"):
            self.reconcile()
        assert "verify" not in self.runtime.calls
        assert "MILESTONE FAIL: cmk-reconcile/activation" in caplog.text

    def test_failed_endpoint_verification_is_not_success(self, caplog):
        def fail(*args):
            raise ReconciliationError("TLS endpoint unavailable")

        self.runtime.verify = fail
        with pytest.raises(ReconciliationError, match="TLS endpoint"):
            self.reconcile()
        assert "MILESTONE FAIL: cmk-reconcile/runtime" in caplog.text

    def test_superseded_event_cannot_activate_an_old_address(self):
        def refresh(hostname, address):
            self.runtime.calls.append("cache")

        self.runtime.refresh_dns = refresh
        with pytest.raises(SupersededCatalogRequest):
            self.reconcile(current=lambda: "cache" not in self.runtime.calls)
        assert "reload" not in self.runtime.calls

    def test_dns_change_during_work_does_not_activate_stale_address(self):
        def refresh(hostname, address):
            self.runtime.address = "10.8.0.77"

        self.runtime.refresh_dns = refresh
        with pytest.raises(ReconciliationError, match="DNS changed"):
            self.reconcile()
        assert "reload" not in self.runtime.calls


class TestCatalogQueue:
    def test_coalesces_and_does_not_acknowledge_newer_requests(self, tmp_path):
        store = CatalogRequestStore(tmp_path)
        first = store.put("client1", "10.8.0.2")
        second = store.put("client1", "10.8.0.3")
        assert not store.acknowledge(first)
        assert store.get("client1") == second
        assert (tmp_path / "client1.json").stat().st_mode & 0o777 == 0o600

    def test_event_during_reconciliation_processes_newest_address(self, tmp_path):
        store = CatalogRequestStore(tmp_path)
        store.put("client1", "10.8.0.2")
        seen = []

        def reconcile(address, current):
            seen.append(address)
            if len(seen) == 1:
                store.put("client1", "10.8.0.3")
                assert not current()
                raise SupersededCatalogRequest()

        CatalogQueueWorker(store, reconcile).run("client1")
        assert seen == ["10.8.0.2", "10.8.0.3"]
        assert store.get("client1") is None

    def test_failure_and_restart_preserve_request(self, tmp_path):
        store = CatalogRequestStore(tmp_path)
        request = store.put("client1", "10.8.0.2")

        def fail(*args):
            raise ReconciliationError("failed")

        with pytest.raises(ReconciliationError):
            CatalogQueueWorker(store, fail).run("client1")
        assert CatalogRequestStore(tmp_path).get("client1") == request

    def test_event_after_success_before_ack_is_not_lost(self, tmp_path):
        store = CatalogRequestStore(tmp_path)
        store.put("client1", "10.8.0.2")
        calls = []

        def reconcile(address, current):
            calls.append(address)
            if len(calls) == 1:
                store.put("client1", "10.8.0.4")

        CatalogQueueWorker(store, reconcile).run("client1")
        assert calls == ["10.8.0.2", "10.8.0.4"]

    @pytest.mark.parametrize("client,ip", [("../../etc/bad", "10.8.0.2"),
        ("bad;name", "10.8.0.2"), ("client1", "0.0.0.0"),
        ("client1", "127.0.0.1"), ("client1", "not-an-ip")])
    def test_invalid_event_rejected(self, tmp_path, client, ip):
        with pytest.raises(ValueError):
            CatalogRequestStore(tmp_path).put(client, ip)
