"""Real TLS regression tests: routing IP is not the certificate identity."""

import json
import socket
import ssl
import subprocess
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests

from dwlabcmkapi.api_client import CheckmkRestClient
from dwlabcmkapi.api_credentials import RestAPIcredentials
from dwlabcmkapi.connection_target import AddressTargetHttpsAdapter


class LocalHttpsServer:
    """Disposable CA, server certificate, HTTPS endpoint and observed identities."""

    def __init__(self, root):
        self.root = root
        self.hosts, self.sni = [], []
        self.server = None

    def _openssl(self, *args):
        subprocess.run(["openssl", *args], cwd=self.root, check=True,
                       capture_output=True, text=True)

    def __enter__(self):
        self._openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", "ca.key", "-out", "ca.crt", "-days", "1", "-subj", "/CN=Test CA",
            "-addext", "basicConstraints=critical,CA:TRUE")
        self._openssl("req", "-new", "-newkey", "rsa:2048", "-nodes",
            "-keyout", "server.key", "-out", "server.csr", "-subj", "/CN=api.example.invalid")
        (self.root / "extensions").write_text(
            "subjectAltName=DNS:api.example.invalid\n"
            "basicConstraints=critical,CA:FALSE\nextendedKeyUsage=serverAuth\n")
        self._openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.crt",
            "-CAkey", "ca.key", "-CAcreateserial", "-out", "server.crt", "-days", "1",
            "-extfile", "extensions")
        observed = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                observed.hosts.append(self.headers.get("Host"))
                if self.path in {"/relative", "/foreign", "/downgrade"}:
                    self.send_response(302)
                    destination = {"/relative": "/version",
                        "/foreign": "https://elsewhere.example.invalid/version",
                        "/downgrade": "http://api.example.invalid/version"}[self.path]
                    self.send_header("Location", destination)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({"site": "central"}).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.root / "server.crt", self.root / "server.key")
        context.set_servername_callback(lambda sock, name, ctx: self.sni.append(name))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def client(self, hostname="api.example.invalid", verify=None):
        return CheckmkRestClient(
            f"https://{hostname}:{self.server.server_port}", "Bearer test-token",
            verify=str(self.root / "ca.crt") if verify is None else verify,
            connection_address="127.0.0.1", timeout=3)


@pytest.fixture(scope="module")
def endpoint(tmp_path_factory):
    with LocalHttpsServer(tmp_path_factory.mktemp("loopback-https")) as server:
        yield server


class TestAddressTargetHttps:
    def test_initial_version_lookup_also_uses_loopback(self, endpoint, monkeypatch):
        original = socket.getaddrinfo

        def local_only(host, *args, **kwargs):
            assert host == "127.0.0.1", f"Bootstrap attempted provider DNS: {host}"
            return original(host, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", local_only)
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(endpoint.root / "ca.crt"))
        credentials = RestAPIcredentials(
            cmkHostname="api", cmkDomain=f"example.invalid:{endpoint.server.server_port}",
            cmkSiteName="central", username="test", password="test",
            connection_address="127.0.0.1")
        assert credentials.version.site == "central"
        assert credentials.create_client().connection_address == "127.0.0.1"

    def test_no_provider_dns_or_proxy_needed_host_and_sni_preserved(self, endpoint, monkeypatch):
        original = socket.getaddrinfo

        def local_only(host, *args, **kwargs):
            assert host == "127.0.0.1", f"Unexpected DNS dependency: {host}"
            return original(host, *args, **kwargs)

        monkeypatch.setattr(socket, "getaddrinfo", local_only)
        monkeypatch.setenv("HTTPS_PROXY", "http://unreachable.invalid:9999")
        response = endpoint.client().get("/version", headers={"Host": "untrusted.invalid"})
        assert response.json() == {"site": "central"}
        assert endpoint.hosts[-1] == f"api.example.invalid:{endpoint.server.server_port}"
        assert endpoint.sni[-1] == "api.example.invalid"
        assert response.url.startswith("https://api.example.invalid:")

    def test_certificate_hostname_mismatch_is_rejected(self, endpoint):
        with pytest.raises(requests.exceptions.SSLError):
            endpoint.client(hostname="wrong.example.invalid").get("/version")

    def test_explicit_ca_environment_is_honored_without_environment_proxy(self, endpoint, monkeypatch):
        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(endpoint.root / "ca.crt"))
        monkeypatch.setenv("HTTPS_PROXY", "http://unreachable.invalid:9999")
        client = CheckmkRestClient(
            f"https://api.example.invalid:{endpoint.server.server_port}",
            "Bearer test-token", connection_address="127.0.0.1")
        assert client.get("/version").status_code == 200

    def test_untrusted_ca_is_rejected(self, endpoint):
        with pytest.raises(requests.exceptions.SSLError):
            endpoint.client(verify=True).get("/version")

    @pytest.mark.parametrize("verify", [False, None, ""])
    def test_disabling_certificate_verification_is_rejected(self, endpoint, verify):
        with pytest.raises(ValueError, match="requires certificate verification"):
            replace(endpoint.client(), verify=verify).get("/version")

    def test_same_origin_redirect_stays_on_loopback(self, endpoint):
        response = endpoint.client().get("/relative")
        assert response.status_code == 200
        assert len(response.history) == 1

    @pytest.mark.parametrize("path", ["/foreign", "/downgrade"])
    def test_redirect_cannot_escape_identity_or_downgrade_tls(self, endpoint, path):
        with pytest.raises(ValueError, match="different origin or HTTP downgrade"):
            endpoint.client().get(path)

    @pytest.mark.parametrize("address", ["localhost", "invalid", "127.0.0.1:443"])
    def test_target_must_be_a_literal_address(self, address):
        with pytest.raises(ValueError):
            AddressTargetHttpsAdapter("https://api.example.invalid", address)
