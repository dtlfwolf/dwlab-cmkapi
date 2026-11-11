"""A started, rejected or failed activation is not a completed registration."""

from types import SimpleNamespace

import pytest

from dwlabcmkapi.operations import ActivationGateway, HostManagementGateway
from test_adapters import _credentials_stub


class Api:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append(("GET", path, kwargs))
        return self.responses.pop(0)

    def post(self, path, **kwargs):
        self.calls.append(("POST", path, kwargs))
        return self.responses.pop(0)


class TestActivationCompletion:
    identifier = "c123e01b-95ab-4898-b12e-859193ea30f5"

    def response(self, code, data):
        return SimpleNamespace(status_code=code, headers={"ETag": "etag"}, json=lambda: data)

    def gateway(self, *responses):
        gateway = ActivationGateway(_credentials_stub())
        gateway._client = Api(responses)
        return gateway

    def test_no_pending_changes_do_not_trigger_activation(self):
        gateway = self.gateway(self.response(200, {"value": []}))
        gateway.activate_and_wait("central")
        assert len(gateway._client.calls) == 1

    def test_waits_until_target_site_success_without_forcing_foreign_changes(self):
        gateway = self.gateway(
            self.response(200, {"value": [{"id": "pending"}]}),
            self.response(200, {"id": self.identifier}),
            self.response(200, {"extensions": {"is_running": True}}),
            self.response(200, {"extensions": {"is_running": False,
                "status_per_site": [{"site": "central", "state": "success"}]}}))
        sleeps = []
        gateway.activate_and_wait("central", sleep=sleeps.append)
        assert sleeps == [1]
        assert gateway._client.calls[1][2]["json_body"] == {
            "redirect": False, "sites": ["central"], "force_foreign_changes": False}

    @pytest.mark.parametrize("code", [409, 412, 422])
    def test_rejection_does_not_return_success(self, code):
        gateway = self.gateway(self.response(200, {"value": [{"id": "pending"}]}),
                               self.response(code, {"detail": "refused"}))
        with pytest.raises(RuntimeError, match=f"HTTP {code}"):
            gateway.activate_and_wait("central")

    @pytest.mark.parametrize("states", [[], [{"site": "central", "state": "error"}],
        [{"site": "central", "state": "warning"}], [{"site": "other", "state": "success"}]])
    def test_completion_requires_success_on_target_site(self, states):
        gateway = self.gateway(self.response(200, {"value": [{"id": "pending"}]}),
            self.response(200, {"id": self.identifier}),
            self.response(200, {"extensions": {"is_running": False, "status_per_site": states}}))
        with pytest.raises(RuntimeError, match="failed or unverified"):
            gateway.activate_and_wait("central")

    def test_running_activation_has_bounded_deadline(self):
        gateway = self.gateway(self.response(200, {"value": [{"id": "pending"}]}),
            self.response(200, {"id": self.identifier}),
            self.response(200, {"extensions": {"is_running": True}}))
        clock = iter([0, 999])
        with pytest.raises(RuntimeError, match="timed out"):
            gateway.activate_and_wait("central", monotonic=lambda: next(clock))

    @pytest.mark.parametrize("code", [400, 403, 406, 409, 415])
    def test_discovery_failure_is_not_silently_suppressed(self, code):
        gateway = HostManagementGateway(_credentials_stub())
        gateway._client = Api([self.response(code, {"detail": "discovery failed"})])
        with pytest.raises(RuntimeError, match="Service discovery failed"):
            gateway.run_discovery("client.vpn.test", mode="new")
