"""Site-Python stdin/stdout adapter for authenticated, socket-free REST calls.

This installed source is executed as the site's OS identity by the root-only
bootstrap backend. Checkmk and Flask remain dependencies of that native site,
not dependencies of the independently installed DW-Lab wheel.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json
import os
import pwd
import re
import sys


class NativeAccountRunner:
    """Run one authenticated REST call without forwarding a response body."""

    def execute(self, request: dict) -> dict:
        """Return only status, ETag and non-secret account attributes."""
        site = request["site"]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", site):
            raise ValueError("Invalid site")
        path = request["path"]
        if path not in {
            "/domain-types/user_config/collections/all",
            "/objects/user_config/cmkadmin",
            "/objects/user_config/dwlabcmkadm",
            "/objects/user_config/dwlab-automation",
            "/domain-types/user_role/collections/all",
            "/objects/user_role/dwlab_automation",
            "/version",
            "/domain-types/activation_run/collections/pending_changes",
            "/domain-types/activation_run/actions/activate-changes/invoke",
            "/domain-types/site_connection/collections/all",
        } and not re.fullmatch(r"/objects/activation_run/[0-9a-f-]{36}", path):
            raise ValueError("Unsupported account operation")
        if request["method"] not in {"GET", "POST", "PUT"}:
            raise ValueError("Unsupported account operation")
        if request["username"] not in {"cmkadmin", "dwlabcmkadm", "dwlab-automation"}:
            raise ValueError("Unsupported account identity")
        password = request["password"]
        legacy = request.get("legacy_migration") is True and request["username"] == "cmkadmin"
        if (not isinstance(password, str) or not 1 <= len(password) <= 1024
                or any(c in password for c in "\r\n\x00")
                or (not legacy and not re.fullmatch(r"[0-9a-f]{64}", password))):
            raise ValueError("Invalid secret format")
        account = pwd.getpwnam(site)
        if (os.geteuid(), os.getegid()) != (account.pw_uid, account.pw_gid):
            raise ValueError("Native helper requires the real site OS identity")
        from cmk.ccc import version
        from cmk.ccc.site import omd_site
        from cmk.ccc.version import edition
        from cmk.utils import paths
        from cmk.gui import log, main_modules
        from cmk.gui.wsgi.app import make_wsgi_app

        if site != omd_site() or not version.__version__.startswith(("2.4.", "2.5.")):
            raise ValueError("Site context or native version mismatch")
        log.init_logging()
        site_edition = edition(paths.omd_root)
        if version.__version__.startswith("2.4."):
            main_modules.load_plugins()
        else:
            main_modules.register(site_edition)
        app = make_wsgi_app(site_edition)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {request['username']} {request['password']}",
        }
        if request.get("etag"):
            headers["If-Match"] = request["etag"]
        # No REMOTE_USER override, testing-mode bypass or retained login cookie.
        with app.test_client(use_cookies=False) as client:
            if "/user_role/" in path:
                # The vendor registers dynamic permissions while listing roles,
                # but validates PUT fields before entering its update endpoint.
                # Initialize through an authenticated read, not a bypass or a
                # hand-maintained subset that would leave inherited rights on.
                preflight = client.open(
                    f"/{site}/check_mk/api/1.0/domain-types/user_role/collections/all",
                    method="GET", base_url="https://localhost", headers=headers,
                    follow_redirects=False,
                )
                if preflight.status_code != 200:
                    return {"status": preflight.status_code, "etag": None}
            response = client.open(
                f"/{site}/check_mk/api/1.0{path}", method=request["method"],
                base_url="https://localhost", headers=headers,
                json=request.get("body"), follow_redirects=False,
            )
        result = {"status": response.status_code, "etag": response.headers.get("ETag")}
        data = response.get_json(silent=True)
        if response.status_code == 200 and isinstance(data, dict):
            extensions = data.get("extensions", {})
            auth = extensions.get("auth_option", {})
            result["user"] = {
                "id": data.get("id"), "roles": extensions.get("roles"),
                "disabled": extensions.get("disable_login"),
                "auth_type": auth.get("auth_type"),
                "store_secret": auth.get("store_automation_secret", False),
            }
            if path == "/domain-types/activation_run/collections/pending_changes":
                result["pending_changes"] = data.get("value")
            elif path.startswith("/objects/activation_run/") or path.endswith("/activate-changes/invoke"):
                result["activation"] = {
                    "id": data.get("id"), "is_running": extensions.get("is_running"),
                    "status_per_site": extensions.get("status_per_site"),
                }
            elif path == "/domain-types/site_connection/collections/all":
                result["site_connections"] = [
                    {"id": item.get("id"), "replication_enabled": item.get("extensions", {}).get(
                        "configuration_connection", {}).get("enable_replication")}
                    for item in data.get("value", [])
                ]
            if "/user_role/" in path:
                from cmk.gui import permissions

                result["role"] = {
                    "id": data.get("id"), "basedon": extensions.get("basedon"),
                    "builtin": extensions.get("builtin"),
                    "permissions": extensions.get("permissions"),
                    "available_permissions": sorted(permissions.permission_registry.keys()),
                }
        return result

    def run(self) -> int:
        """Consume secrets from stdin; suppress framework output and errors."""
        try:
            raw = sys.stdin.buffer.read(131073)
            if len(raw) > 131072:
                raise ValueError("Request too large")
            request = json.loads(raw)
            with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
                result = self.execute(request)
        except Exception as error:
            # Neither exceptions nor API error bodies may echo request secrets.
            code = "native-account-operation-failed"
            if isinstance(error, PermissionError):
                code = "native-filesystem-permission-denied"
            elif isinstance(error, ImportError):
                code = "native-dependency-unavailable"
            print(json.dumps({"error": code}))
            return 1
        print(json.dumps(result))
        return 0


if __name__ == "__main__":
    raise SystemExit(NativeAccountRunner().run())
