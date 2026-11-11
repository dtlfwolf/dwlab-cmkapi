"""Reconcile VPN clients against DNS and the running monitoring core."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Callable, ContextManager, Protocol

from .domain import CentralServer, ClientInstance
from .services import ClientCatalogResult, ClientCatalogService, SiteConnectionState

LOGGER = logging.getLogger(__name__)


class ReconciliationError(RuntimeError):
    """A client could not be verified within the configured deadline."""


class SupersededCatalogRequest(ReconciliationError):
    """A newer VPN connection superseded the request being processed."""


class CatalogRuntime(Protocol):
    """Site-local operations required in addition to the public REST API."""

    def lock(self) -> ContextManager[None]: ...
    def resolve(self, hostname: str) -> set[str]: ...
    def refresh_dns(self, hostname: str, address: str) -> None: ...
    def core_address(self, hostname: str) -> str: ...
    def reload(self) -> None: ...
    def verify(self, hostname: str, address: str,
               connection: SiteConnectionState) -> None: ...


class ClientReconciliationService:
    """Serialize catalog changes and verify their effective runtime result.

    This service is deliberately separate from REST-only catalog management:
    its runtime port must be supplied by a site-local adapter or equivalent
    authorized management service.
    """

    def __init__(self, catalog: ClientCatalogService, runtime: CatalogRuntime,
                 timeout: float = 60, interval: float = 1,
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if timeout <= 0 or interval <= 0:
            raise ValueError("DNS timeout and retry interval must be positive")
        self._catalog = catalog
        self._runtime = runtime
        self._timeout = timeout
        self._interval = interval
        self._clock = monotonic
        self._sleep = sleep

    def reconcile(self, central: CentralServer, client: ClientInstance,
                  expected_address: str | None = None,
                  is_current: Callable[[], bool] = lambda: True
                  ) -> ClientCatalogResult:
        """Repair stale addresses without storing static VPN IP attributes."""
        hostname = central.managed_host_name(client.instance_name)
        with self._runtime.lock():
            with self._milestone("dns", hostname):
                address = self._wait_for_dns(hostname, expected_address, is_current)
            with self._milestone("catalog", hostname, address):
                self._require_current(is_current)
                result = self._catalog.catalog_client(central, client, defer_activation=True)
            with self._milestone("dns-cache", hostname, address):
                self._require_current(is_current)
                self._runtime.refresh_dns(hostname, address)
            with self._milestone("activation", hostname, address):
                self._require_current(is_current)
                self._require_dns(hostname, address)
                self._catalog.activate(central.site_name)
                self._require_current(is_current)
                self._require_dns(hostname, address)
                if self._runtime.core_address(hostname) != address:
                    self._runtime.reload()
            with self._milestone("discovery", hostname, address):
                self._require_current(is_current)
                self._catalog.discover(hostname)
                self._require_current(is_current)
                self._require_dns(hostname, address)
                self._catalog.activate(central.site_name)
            with self._milestone("runtime", hostname, address):
                self._require_current(is_current)
                self._require_dns(hostname, address)
                connection = self._catalog.get_connection(client.site_name)
                self._runtime.verify(hostname, address, connection)
                self._require_current(is_current)
                self._require_dns(hostname, address)
            return result

    def _wait_for_dns(self, hostname, expected, is_current):
        deadline = self._clock() + self._timeout
        actual = set()
        while True:
            self._require_current(is_current)
            actual = self._runtime.resolve(hostname)
            if len(actual) == 1 and (expected is None or expected in actual):
                return next(iter(actual))
            if self._clock() >= deadline:
                raise ReconciliationError(
                    f"DNS timeout: host={hostname} expected={expected} actual={sorted(actual)}")
            self._sleep(self._interval)

    def _require_dns(self, hostname, address):
        actual = self._runtime.resolve(hostname)
        if actual != {address}:
            raise ReconciliationError(
                f"DNS changed: host={hostname} expected={address} actual={sorted(actual)}")

    def _require_current(self, is_current):
        if not is_current():
            raise SupersededCatalogRequest("A newer VPN event is queued")

    @contextmanager
    def _milestone(self, phase, hostname, address=None):
        started = self._clock()
        context = f"host={hostname} expected_address={address}"
        LOGGER.info("MILESTONE START: cmk-reconcile/%s %s", phase, context)
        try:
            yield
        except Exception:
            LOGGER.exception("MILESTONE FAIL: cmk-reconcile/%s %s duration=%.3fs",
                             phase, context, self._clock() - started)
            raise
        LOGGER.info("MILESTONE PASS: cmk-reconcile/%s %s duration=%.3fs",
                    phase, context, self._clock() - started)
