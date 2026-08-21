from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol

from .domain import CentralServer, ClientInstance


def _require_non_empty_string(field_name: str, value: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if value == "":
        raise ValueError(f"{field_name} cannot be empty")


@dataclass(frozen=True)
class ClientArtifactTarget:
    name: str
    variant: str = ""

    def __post_init__(self):
        _require_non_empty_string("name", self.name)
        if not isinstance(self.variant, str):
            raise TypeError("variant must be a string")

    @property
    def key(self) -> str:
        if self.variant:
            return f"{self.name}:{self.variant}"
        return self.name


@dataclass(frozen=True)
class ClientArtifactRequest:
    central_server: CentralServer
    client_instance: ClientInstance
    target: ClientArtifactTarget
    output_directory: Path
    artifact_name: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.output_directory, Path):
            raise TypeError("output_directory must be a pathlib.Path")
        if self.artifact_name and not isinstance(self.artifact_name, str):
            raise TypeError("artifact_name must be a string")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")

    @property
    def resolved_artifact_name(self) -> str:
        if self.artifact_name:
            return self.artifact_name
        return self.client_instance.instance_name


@dataclass(frozen=True)
class ClientArtifact:
    target: ClientArtifactTarget
    artifact_path: Path
    package_name: str

    def __post_init__(self):
        if not isinstance(self.artifact_path, Path):
            raise TypeError("artifact_path must be a pathlib.Path")
        _require_non_empty_string("package_name", self.package_name)


class ClientArtifactBuilder(Protocol):
    def supports(self, target: ClientArtifactTarget) -> bool:
        ...

    def build(self, request: ClientArtifactRequest) -> ClientArtifact:
        ...
