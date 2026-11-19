"""Site-Python stdin/stdout adapter for authenticated, socket-free REST calls.

This installed source is executed as the site's OS identity by the root-only
bootstrap backend. Checkmk and Flask remain dependencies of that native site,
not dependencies of the independently installed DW-Lab wheel.
"""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json
import os
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
        } or request["method"] not in {"GET", "POST", "PUT"}:
            raise ValueError("Unsupported account operation")
        if request["username"] not in {"cmkadmin", "dwlabcmkadm", "dwlab-automation"}:
            raise ValueError("Unsupported account identity")
        if not re.fullmatch(r"[0-9a-f]{64}", request["password"]):
            raise ValueError("Invalid secret format")
        from cmk.ccc import version
        from cmk.ccc.site import omd_site
        from cmk.ccc.version import edition
        from cmk.utils import paths
        from cmk.gui import log, main_modules
        from cmk.gui.wsgi.app import make_wsgi_app

        if site != omd_site() or not version.__version__.startswith(("2.4.", "2.5.")):
            raise ValueError("Site context or native version mismatch")
        log.init_logging()
        main_modules.load_plugins()
        app = make_wsgi_app(edition(paths.omd_root))
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {request['username']} {request['password']}",
        }
        if request.get("etag"):
            headers["If-Match"] = request["etag"]
        # No REMOTE_USER override, testing-mode bypass or retained login cookie.
        with app.test_client(use_cookies=False) as client:
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
        return result

    def run(self) -> int:
        """Consume secrets from stdin; suppress framework output and errors."""
        try:
            raw = sys.stdin.buffer.read(16385)
            if len(raw) > 16384:
                raise ValueError("Request too large")
            request = json.loads(raw)
            with open(os.devnull, "w") as sink, redirect_stdout(sink), redirect_stderr(sink):
                result = self.execute(request)
        except Exception:
            # Neither exceptions nor API error bodies may echo request secrets.
            print(json.dumps({"error": "native-account-operation-failed"}))
            return 1
        print(json.dumps(result))
        return 0


if __name__ == "__main__":
    raise SystemExit(NativeAccountRunner().run())
