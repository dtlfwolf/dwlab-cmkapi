"""The container delivery must use the same core services without pip."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from dwlabcmkapi.portable_bootstrap import PortableBootstrapBundle


def test_exact_core_sources_and_manifest_are_exported(tmp_path):
    target = tmp_path / "portable"
    PortableBootstrapBundle().write(target)
    manifest = json.loads((target / "manifest.json").read_text())
    from dwlabcmkapi import credential_bootstrap
    source = Path(credential_bootstrap.__file__).parent
    for module in PortableBootstrapBundle.MODULES:
        actual = (target / "dwlab_cmk_bootstrap" / module).read_bytes()
        assert actual == (source / module).read_bytes()
        assert hashlib.sha256(actual).hexdigest() == manifest["sha256"][module]
    assert manifest["product"] == "dwlabcmkapi"


def test_portable_cli_imports_without_site_packages_or_dwlab_dependencies(tmp_path):
    target = tmp_path / "portable"
    PortableBootstrapBundle().write(target)
    result = subprocess.run([sys.executable, "-S", str(target / "run.py"), "--help"],
                            capture_output=True, text=True,
                            env={"PATH": os.environ["PATH"]}, cwd="/", check=False)
    assert result.returncode == 0, result.stderr
    assert "--credential-root" in result.stdout
    assert "--password" not in result.stdout


def test_bundle_never_overwrites_an_existing_directory(tmp_path):
    with pytest.raises(FileExistsError):
        PortableBootstrapBundle().write(tmp_path)
