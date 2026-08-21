from .artifacts import ClientArtifact, ClientArtifactBuilder, ClientArtifactRequest


class ClientArtifactBuildService:
    def __init__(self, builders: list[ClientArtifactBuilder]):
        if len(builders) == 0:
            raise ValueError("builders cannot be empty")
        self._builders = list(builders)

    def build_artifact(self, request: ClientArtifactRequest) -> ClientArtifact:
        for builder in self._builders:
            if builder.supports(request.target):
                return builder.build(request)

        raise RuntimeError(f"No builder registered for target {request.target.key}")
