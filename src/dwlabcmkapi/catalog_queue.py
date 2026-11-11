"""Durable, coalescing VPN catalog requests independent of OpenVPN."""

from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .reconciliation import ReconciliationError, SupersededCatalogRequest


@dataclass(frozen=True)
class CatalogRequest:
    """Latest connection generation and expected VPN address for a client."""

    client: str
    address: str
    generation: str


class CatalogRequestStore:
    """Atomically replace requests; never acknowledge a newer connection."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, client: str) -> Path:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", client):
            raise ValueError("Invalid Checkmk client site name")
        return self.root / f"{client}.json"

    @contextmanager
    def _lock(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.root / ".queue.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def put(self, client: str, address: str) -> CatalogRequest:
        """Persist the event before asking a scheduler to process it."""
        path = self._path(client)
        ip = ipaddress.IPv4Address(address)
        if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
            raise ValueError("Invalid VPN client address")
        request = CatalogRequest(client, str(ip), uuid.uuid4().hex)
        with self._lock():
            temporary = path.with_suffix(f".{request.generation}.tmp")
            try:
                with temporary.open("x") as output:
                    os.chmod(temporary, 0o600)
                    json.dump(request.__dict__, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return request

    def get(self, client: str) -> CatalogRequest | None:
        """Return an atomic snapshot of the latest connection event."""
        path = self._path(client)
        try:
            return CatalogRequest(**json.loads(path.read_text()))
        except FileNotFoundError:
            return None

    def acknowledge(self, request: CatalogRequest) -> bool:
        """Remove only the exact request which was successfully verified."""
        with self._lock():
            if self.get(request.client) != request:
                return False
            self._path(request.client).unlink()
            return True


class CatalogQueueWorker:
    """Process the newest event, leaving failures queued for scheduled retry."""

    def __init__(self, store: CatalogRequestStore, reconcile: Callable,
                 max_generations: int = 5) -> None:
        self._store, self._reconcile = store, reconcile
        self._max_generations = max_generations

    def run(self, client: str) -> None:
        """Coalesce rapid reconnects without acknowledging an obsolete result."""
        for _ in range(self._max_generations):
            request = self._store.get(client)
            if request is None:
                return
            try:
                self._reconcile(
                    request.address,
                    lambda: self._store.get(client) == request)
            except SupersededCatalogRequest:
                continue
            if self._store.acknowledge(request):
                return
        raise ReconciliationError("VPN events changed repeatedly; latest request remains queued")
