from pathlib import Path

import pytest

from dwlabcmkapi.artifacts import (
    ClientArtifact,
    ClientArtifactRequest,
    ClientArtifactTarget,
)
from dwlabcmkapi.artifact_services import ClientArtifactBuildService
from dwlabcmkapi.domain import CentralServer, ClientInstance, CmkSiteIdentity


class StubBuilder:
    def __init__(self, supported_key: str, result_suffix: str):
        self.supported_key = supported_key
        self.result_suffix = result_suffix

    def supports(self, target: ClientArtifactTarget) -> bool:
        return target.key == self.supported_key

    def build(self, request: ClientArtifactRequest) -> ClientArtifact:
        return ClientArtifact(
            target=request.target,
            artifact_path=request.output_directory / f"{request.resolved_artifact_name}{self.result_suffix}",
            package_name=request.resolved_artifact_name,
        )


def make_request(target_name: str, variant: str = "", artifact_name: str = "") -> ClientArtifactRequest:
    central = CentralServer(
        identity=CmkSiteIdentity(site_name="central", hostname="central-01", domain="example.test"),
        ovpn_network="managed",
        ovpn_network_domain="example.test",
    )
    client = ClientInstance(
        identity=CmkSiteIdentity(site_name="client1", hostname="client-01", domain="example.test")
    )
    return ClientArtifactRequest(
        central_server=central,
        client_instance=client,
        target=ClientArtifactTarget(name=target_name, variant=variant),
        output_directory=Path("/tmp/out"),
        artifact_name=artifact_name,
    )


def test_target_key_uses_variant_when_present():
    target = ClientArtifactTarget(name="container", variant="docker")
    assert target.key == "container:docker"


def test_request_uses_instance_name_when_artifact_name_missing():
    request = make_request("os-package")
    assert request.resolved_artifact_name == "client1"


def test_request_prefers_explicit_artifact_name():
    request = make_request("os-package", artifact_name="customer-a")
    assert request.resolved_artifact_name == "customer-a"


def test_build_service_selects_matching_builder():
    request = make_request("os-package", "deb")
    service = ClientArtifactBuildService(
        [
            StubBuilder("container:docker", ".tar"),
            StubBuilder("os-package:deb", ".deb"),
        ]
    )

    artifact = service.build_artifact(request)

    assert artifact.package_name == "client1"
    assert artifact.artifact_path == Path("/tmp/out/client1.deb")


def test_build_service_raises_when_target_is_unknown():
    request = make_request("orchestrator", "kubernetes")
    service = ClientArtifactBuildService([StubBuilder("os-package:deb", ".deb")])

    with pytest.raises(RuntimeError, match="orchestrator:kubernetes"):
        service.build_artifact(request)


def test_build_service_requires_at_least_one_builder():
    with pytest.raises(ValueError, match="builders cannot be empty"):
        ClientArtifactBuildService([])


def test_request_rejects_non_path_output_directory():
    with pytest.raises(TypeError, match="output_directory"):
        ClientArtifactRequest(  # type: ignore[arg-type]
            central_server=CentralServer(
                identity=CmkSiteIdentity(site_name="central", hostname="central-01", domain="example.test"),
                ovpn_network="managed",
                ovpn_network_domain="example.test",
            ),
            client_instance=ClientInstance(
                identity=CmkSiteIdentity(site_name="client1", hostname="client-01", domain="example.test")
            ),
            target=ClientArtifactTarget(name="os-package"),
            output_directory="/tmp/out",
        )
