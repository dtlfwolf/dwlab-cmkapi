# dwlabcmkapi

`dwlabcmkapi` provides a simple and extensible Python interface to interact with Checkmk servers, manage monitoring configurations, schedule backups, and integrate Checkmk operations into your custom workflows.

## ✨ Features

- Connect to and authenticate with Checkmk servers
- Automate host and service management
- Schedule and execute backup jobs
- Integrate with existing Python systems or automation pipelines
- Modular design for easy extension

## 📦 Installation

Install the package and its dependencies with pip:

```bash
pip install dwlabcmkapi

For local development in this workspace:

```bash
python3 -m pip install -e ../dwlabbasicpy
python3 -m pip install -e ../dwlabbackup
python3 -m pip install -e .
```

## 🧱 Packaging

`dwlabcmkapi` uses a standard `src/` layout and is built with setuptools:

```bash
python3 -m build --no-isolation
```

The package ships its logging configuration from `src/dwlabcmkapi/etc/logging.yaml`.

### VPN-Side Remote Web URLs (0.20.3)

`CentralServer.remote_instance_port` defaults to **5000**, the Checkmk web port
inside the client VPN. New site connections use
`http://<client>.<vpn-domain>:5000/<site>/` as their URL prefix and
`http://<client>.<vpn-domain>:5000/<site>/check_mk/` as the remote site URL.
An explicit constructor port remains supported. This setting does not change
the Docker host's separately published port (normally 8080).

Build the independent wheel and its checksum using `make rebuild-wheel`.
Install the new wheel in the central server's runtime, or rebuild its delivery
artifacts so they bundle this release. Merely building it does not update a
running server. Registration currently preserves existing site connections;
their old URL prefixes must be corrected separately, not by deleting the site.

## 🧪 Development

For local test runs inside the DW-Lab workspace:

```bash
python3 -m pytest
```

The root `conftest.py` adds the local `src/` tree and sibling package `src/` directories to `sys.path`, matching the editable workspace setup.

## VPN Reconnect Reconciliation (0.21.0)

`ClientReconciliationService` complements the REST-only `ClientCatalogService`.
Inject a `CatalogRuntime` implementation to reconcile new **and existing** hosts.
The Linux `LocalCheckmkRuntime` runs DNS lookups, Checkmk commands and probes as
the OMD site user; it requires local root privileges and an existing OMD site.
It does not require any other product's source checkout.

The sequence is: wait for the event's IPv4 address in DNS, ensure catalog objects,
refresh and verify Checkmk's persistent address cache, regenerate stale core
configuration, then verify a fresh UP host check and the actual remote Livestatus
transport. No static VPN address is written to host attributes. An unchanged
reconnect verifies runtime without regenerating the core. TLS encryption and
certificate verification follow the site's existing connection settings.
Pending API changes are activated with `force_foreign_changes=False`; the worker
polls the activation object until its target site reports success. Rejected,
failed or timed-out activations are failures, not successful registration.
Add-only service discovery also runs on reconnect, allowing interrupted first
registrations to recover without removing existing services.

`LocalCheckmkRuntime(..., allow_activation=True)` is an explicit opt-in:
regeneration is **site-wide** and can activate other pending administrator
configuration. Coordinate interactive changes accordingly. Nagios uses `cmk -R`;
CMC uses `cmk -O`. Checkmk cache refresh is also site-wide. The per-site file lock
serializes DW-Lab workers, not external administrator commands. Failures propagate
with `MILESTONE FAIL`, host, expected/actual values, phase and elapsed duration.

`CatalogRequestStore` atomically persists the latest connection address per client.
`CatalogQueueWorker` acknowledges only a successfully verified generation; newer
events supersede older ones and failures remain available for retry. State and
lock paths are injected. These services are independent of OpenVPN and systemd;
the deployment integration supplies scheduling and the event address.

Run independent regression tests with `make test`; build with `make wheel`.
Tests cover first registration, unchanged/changed reconnects, invalid core
addresses, delayed DNS, activation/probe failures, overlapping generations,
command quoting, transport settings and queue recovery.

## Local API Connections (0.22.0)

The provider hostname remains the HTTPS identity. An explicit
`RestAPIcredentials(..., connection_address="127.0.0.1")` or
`CheckmkRestClient(..., connection_address="127.0.0.1")` changes only the network
destination. HTTP Host, TLS SNI and certificate hostname verification retain the
original URL hostname. Apache must listen on the chosen loopback address and
serve the matching virtual host; its certificate chain must already be trusted.
Do not add `localhost` to certificates or disable verification for this feature.

`load_central_server_config(local_api=True)` selects `cmkLocalApiAddress` from
installation settings, defaulting to `127.0.0.1` when absent. Only literal
loopback IPs are allowed for this setting (`::1` is supported where listening).
The default `local_api=False` and ordinary credentials keep normal DNS-based
connections, so external callers can still select their VPN-facing hostname.

Local address-target sessions bypass environment proxy/netrc settings. Explicit
CA paths remain honored. HTTPS redirects are allowed only within the original
scheme/hostname/port; other origins and HTTP downgrades are rejected before
credentials are transmitted. Requests >= 2.32.3 and urllib3 >= 2.2.3 are required;
the adapter uses the public TLS-context interface, not deprecated adapter hooks.

The TLS integration tests start a disposable localhost HTTPS server and require
`openssl` plus permission to bind a loopback socket. They verify DNS independence,
Host/SNI, trusted and untrusted certificates, hostname mismatch, proxy bypass,
and safe redirects. No running Checkmk instance is needed.
