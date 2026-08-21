from pathlib import Path

from dwlabbasicpy import dwlabRuntimeEnvironment


DEFAULT_SETTINGS_CANDIDATES = (
    Path("/opt/dwlab/dwlab-cmkcentralserver/etc/dw-lab_InstallationSettings.yaml"),
    Path("/opt/dwlab/dwlab-cmkcentralserver-deploy/etc/dw-lab_InstallationSettings.yaml"),
)


def resolve_central_server_settings_file(settings_file: str | Path | None = None) -> Path:
    if settings_file is not None:
        return Path(settings_file)

    for candidate in DEFAULT_SETTINGS_CANDIDATES:
        if candidate.exists():
            return candidate

    return DEFAULT_SETTINGS_CANDIDATES[0]
