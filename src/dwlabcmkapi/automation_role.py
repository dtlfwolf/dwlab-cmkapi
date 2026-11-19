"""An explicit Checkmk automation role without user/security administration."""

from __future__ import annotations

from .credential_bootstrap import BootstrapError, SiteCredentialState


class AutomationRoleProvisioner:
    """Create a dedicated role; deny permissions outside the reviewed allowlist."""

    NAME = "dwlab_automation"
    PATH = "/objects/user_role/" + NAME
    ALLOWED = frozenset({
        "general.use", "general.see_all", "wato.use", "wato.edit",
        "wato.manage_hosts", "wato.edit_hosts", "wato.all_folders",
        "wato.see_all_folders", "wato.sites", "wato.activate",
        "wato.download_agents",
        "wato.services", "wato.service_discovery_to_monitored",
        "wato.service_discovery_to_undecided",
        "wato.service_discovery_to_removed",
    })
    REQUIRED = frozenset({"general.use", "wato.use", "wato.edit", "wato.sites",
                          "wato.activate", "wato.manage_hosts", "wato.edit_hosts",
                          "wato.services", "wato.service_discovery_to_monitored",
                          "wato.service_discovery_to_removed"})

    def __init__(self, transport) -> None:
        self._transport = transport

    def _get(self, state: SiteCredentialState, actor: str, secret: str) -> dict:
        return self._transport.request(state, actor, secret, "GET", self.PATH)

    def assert_absent(self, state: SiteCredentialState) -> None:
        """Do not adopt or overwrite an unrelated customer's existing role."""
        if self._get(state, "cmkadmin", state.bootstrap_password)["status"] != 404:
            raise BootstrapError("Automation role already exists; explicit review is required.")

    def provision(self, state: SiteCredentialState) -> None:
        """Build permissions from the target release's registered permission set."""
        current = self._get(state, "cmkadmin", state.bootstrap_password)
        if current["status"] == 404:
            current = self._transport.request(
                state, "cmkadmin", state.bootstrap_password, "POST",
                "/domain-types/user_role/collections/all",
                body={"role_id": "user", "new_role_id": self.NAME,
                      "new_alias": "DW-Lab site automation"},
            )
        role = current.get("role", {})
        permissions = role.get("available_permissions")
        if (current["status"] != 200 or role.get("id") != self.NAME
                or role.get("builtin") is not False or role.get("basedon") != "user"
                or not isinstance(permissions, list)
                or any(not isinstance(key, str) for key in permissions)
                or not self.REQUIRED.issubset(permissions)):
            raise BootstrapError("Cannot inspect target automation role permissions.")
        desired = {key: "yes" if key in self.ALLOWED else "no" for key in permissions}
        response = self._transport.request(
            state, "cmkadmin", state.bootstrap_password, "PUT", self.PATH,
            body={"new_basedon": "user", "new_permissions": desired},
        )
        if response["status"] != 200:
            raise BootstrapError("Automation role configuration failed.")
        self.verify(state, "cmkadmin", state.bootstrap_password)

    def verify(self, state: SiteCredentialState, actor: str, secret: str) -> None:
        """Reject expanded permissions rather than silently repairing active roles."""
        current = self._get(state, actor, secret)
        role = current.get("role", {})
        permissions = role.get("permissions")
        available = role.get("available_permissions")
        if (current["status"] != 200 or role.get("id") != self.NAME
                or role.get("builtin") is not False or role.get("basedon") != "user"
                or not isinstance(permissions, list) or not isinstance(available, list)
                or any(not isinstance(key, str) for key in permissions + available)
                or not self.REQUIRED.issubset(permissions)
                or set(permissions) != set(available) & self.ALLOWED):
            raise BootstrapError("Automation role does not match the restricted permission policy.")
