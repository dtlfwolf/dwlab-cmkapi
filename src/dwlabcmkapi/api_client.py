from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests


def _default_verify_path() -> str | bool:
    for env_name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        value = Path(str(__import__("os").environ.get(env_name, "")).strip())
        if str(value) and value.is_file():
            return str(value)

    system_bundle = Path("/etc/ssl/certs/ca-certificates.crt")
    if system_bundle.is_file():
        return str(system_bundle)

    return True


@dataclass(frozen=True)
class CheckmkRestClient:
    base_url: str
    authorization: str
    session_factory: Callable[[], requests.Session] = requests.session
    verify: str | bool = _default_verify_path()
    timeout: float = 10.0

    @classmethod
    def from_credentials(cls, cmk_access, api_version: str = "") -> "CheckmkRestClient":
        return cls(
            base_url=cmk_access.get_apiUrl(apiVersion=api_version),
            authorization=cmk_access.credentials,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        session = self.session_factory()
        session.headers["Authorization"] = self.authorization
        session.headers["Accept"] = "application/json"
        session.verify = self.verify
        if headers:
            session.headers.update(headers)

        try:
            return session.request(
                method=method,
                url=f"{self.base_url}{path}",
                json=json_body,
                timeout=self.timeout,
            )
        finally:
            session.close()

    def get(self, path: str, *, headers: dict[str, str] | None = None) -> requests.Response:
        return self.request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        return self.request("POST", path, json_body=json_body, headers=headers)

    def put(
        self,
        path: str,
        *,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> requests.Response:
        return self.request("PUT", path, json_body=json_body, headers=headers)

    def delete(self, path: str, *, headers: dict[str, str] | None = None) -> requests.Response:
        return self.request("DELETE", path, headers=headers)
