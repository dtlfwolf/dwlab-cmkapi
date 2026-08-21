from pathlib import Path

from dwlabcmkapi.retirement_gateways import FilesystemRetirementGateway


def test_filesystem_retirement_gateway_deletes_matching_files(tmp_path):
    gateway = FilesystemRetirementGateway()
    package_dir = tmp_path / "packages"
    package_dir.mkdir()
    keep_file = package_dir / "other-file.txt"
    keep_file.write_text("keep", encoding="utf-8")
    delete_a = package_dir / "dwlab-client01_1.0.deb"
    delete_b = package_dir / "dwlab-client01_1.0.changes"
    delete_a.write_text("a", encoding="utf-8")
    delete_b.write_text("b", encoding="utf-8")

    deleted = gateway.delete_files_with_prefix(str(package_dir), "dwlab-client01")

    assert sorted(Path(path).name for path in deleted) == [
        "dwlab-client01_1.0.changes",
        "dwlab-client01_1.0.deb",
    ]
    assert keep_file.exists()
    assert not delete_a.exists()
    assert not delete_b.exists()
