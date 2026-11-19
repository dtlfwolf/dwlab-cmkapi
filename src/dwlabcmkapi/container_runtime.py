"""Prepare a stopped container's ephemeral runtime before authenticated bootstrap."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shlex
import stat
from typing import Callable

from .credential_bootstrap import BootstrapError, OmdBootstrapBackend, RootBootstrapAuthorization, SiteCredentialState


class ContainerRuntimePreparation:
    """Repair only an empty legacy mountpoint, never recursively change site files."""

    def __init__(self, backend: OmdBootstrapBackend, sites_root: Path,
                 owner_changer: Callable[[int, int, int], None] = os.fchown,
                 logger: logging.Logger | None = None) -> None:
        self._backend, self._root = backend, sites_root
        self._owner_changer = owner_changer
        self._logger = logger or logging.getLogger(__name__)

    def prepare(self, state: SiteCredentialState) -> None:
        """Populate the vendor runtime skeleton as its OS user, with services stopped."""
        RootBootstrapAuthorization().require_root()
        self._logger.info("STEP START: operation=cmk-container-runtime caller_uid=%s site=%s", os.geteuid(), state.site)
        if not self._backend.is_stopped(state.site):
            raise BootstrapError("Container runtime preparation requires a stopped site.")
        path = self._root / state.site / "tmp"
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            raise BootstrapError("Container runtime mountpoint is missing or unsafe.") from None
        try:
            info = os.fstat(descriptor)
            if (info.st_uid, info.st_gid) != (state.uid, state.gid):
                if not state.legacy_migration or info.st_uid != 0 or os.listdir(descriptor):
                    raise BootstrapError("Unexpected container runtime ownership; manual review required.")
                self._owner_changer(descriptor, state.uid, state.gid)
                os.fchmod(descriptor, 0o751)
                self._logger.info("STEP PASS: operation=cmk-container-runtime phase=legacy-empty-mountpoint-repair site=%s", state.site)
            elif stat.S_IMODE(info.st_mode) & 0o002:
                raise BootstrapError("World-writable container runtime mountpoint is refused.")
        finally:
            os.close(descriptor)
        if self._backend._run(["/usr/bin/omd", "config", state.site, "set", "TMPFS", "off"]).returncode:
            raise BootstrapError("Cannot select unprivileged container runtime storage.")
        program = Path(__file__).with_name("native_runtime_runner.py").read_text()
        result = self._backend._run([
            "/usr/sbin/runuser", "--login", state.site, "--command",
            shlex.join(["python3", "-c", program, state.site]),
        ])
        if result.returncode:
            raise BootstrapError("Cannot prepare the stopped container runtime skeleton.")
        self._logger.info("STEP PASS: operation=cmk-container-runtime phase=vendor-skeleton-prepared site=%s", state.site)
