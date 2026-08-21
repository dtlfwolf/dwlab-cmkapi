from pathlib import Path

import dwlabcmkapi


def test_import_exposes_package_modules():
    assert hasattr(dwlabcmkapi, "CheckmkGateway")
    assert hasattr(dwlabcmkapi, "RestAPIcredentials")
    assert hasattr(dwlabcmkapi, "CentralServerManager")


def test_logging_config_is_packaged_in_source_tree():
    package_root = Path(dwlabcmkapi.__file__).resolve().parent
    assert (package_root / "etc" / "logging.yaml").is_file()
