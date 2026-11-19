"""Deliver the core bootstrap services without a container pip toolchain."""

from __future__ import annotations

from importlib.metadata import version
import hashlib
import json
from pathlib import Path


class PortableBootstrapBundle:
    """Package exact core sources under an isolated stdlib-only namespace."""

    MODULES = (
        "credential_bootstrap.py", "account_bootstrap.py", "automation_role.py",
        "native_account_runner.py", "container_bootstrap.py",
    )

    def write(self, destination: Path) -> None:
        """Export code and hashes only; never read installation settings or secrets."""
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=False)
        package = destination / "dwlab_cmk_bootstrap"
        package.mkdir()
        (package / "__init__.py").write_text('"""Portable DW-Lab Checkmk bootstrap."""\n')
        source = Path(__file__).parent
        hashes = {}
        for name in self.MODULES:
            content = (source / name).read_bytes()
            (package / name).write_bytes(content)
            hashes[name] = hashlib.sha256(content).hexdigest()
        (destination / "run.py").write_text(
            "from dwlab_cmk_bootstrap.container_bootstrap import ContainerBootstrapCli\n"
            "raise SystemExit(ContainerBootstrapCli().run())\n"
        )
        (destination / "manifest.json").write_text(json.dumps({
            "product": "dwlabcmkapi", "version": version("dwlabcmkapi"),
            "sha256": hashes,
        }, sort_keys=True) + "\n")
