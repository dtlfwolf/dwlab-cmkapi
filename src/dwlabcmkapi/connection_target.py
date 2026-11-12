"""HTTPS routing independent of the authenticated server identity."""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit

from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter
from urllib3.connectionpool import HTTPSConnectionPool


class AddressTargetHttpsAdapter(HTTPAdapter):
    """Connect to a literal IP while retaining Host, SNI and certificate checks.

    Only one HTTPS origin is authorized. Cross-origin/downgrade redirects and
    proxies are rejected before credentials can be sent to another endpoint.
    Uses the public Requests >= 2.32.3 TLS-context adapter interface.
    """

    def __init__(self, base_url: str, address: str) -> None:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("An HTTPS server identity without URL credentials is required")
        self._hostname = parsed.hostname
        self._port = parsed.port or 443
        self._authority = parsed.netloc
        self._address = str(ip_address(address))
        if not hasattr(HTTPAdapter, "get_connection_with_tls_context"):
            raise RuntimeError("Address-target HTTPS requires requests >= 2.32.3")
        super().__init__()

    def send(self, request: PreparedRequest, stream: bool = False,
             timeout=None, verify=True, cert=None, proxies=None) -> Response:
        """Keep every request, including redirects, inside the authorized origin."""
        parsed = urlsplit(request.url)
        if (parsed.scheme != "https" or parsed.hostname != self._hostname
                or (parsed.port or 443) != self._port
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("Address-target HTTPS refuses a different origin or HTTP downgrade")
        if not verify:
            raise ValueError("Address-target HTTPS requires certificate verification")
        if proxies:
            raise ValueError("Address-target HTTPS does not permit proxies")
        request.headers["Host"] = self._authority
        return super().send(request, stream=stream, timeout=timeout,
                            verify=verify, cert=cert, proxies={})

    def get_connection_with_tls_context(self, request: PreparedRequest,
                                        verify: str | bool,
                                        proxies: dict[str, str] | None = None,
                                        cert: str | tuple[str, str] | None = None
                                        ) -> HTTPSConnectionPool:
        """Build the IP-address pool with the original TLS server identity."""
        if proxies:
            raise ValueError("Address-target HTTPS does not permit proxies")
        host, tls = self.build_connection_pool_key_attributes(request, verify, cert)
        host["host"] = self._address
        tls["server_hostname"] = self._hostname
        tls["assert_hostname"] = self._hostname
        return self.poolmanager.connection_from_host(**host, pool_kwargs=tls)
