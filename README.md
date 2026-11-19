# dwlabcmkapi

`dwlabcmkapi` provides a simple and extensible Python interface to interact with Checkmk servers, manage monitoring configurations, schedule backups, and integrate Checkmk operations into your custom workflows.

## Credential Preparation Foundation (0.23.0)

This is the first implementation increment for CMK-01, not its completed
remediation. The existing central/client deployment flow is deliberately not
rewired yet. No existing accounts or credentials are automatically changed.
The shared runtime now requires independently installable `dwlabbasicpy>=0.23.0`.

The opt-in local preparation API is implemented in
`dwlabcmkapi.credential_bootstrap`. `NewSiteCredentialPreparation` uses explicit
authorization, storage and native-backend interfaces. CLI calls require the
effective OS root identity; environment usernames and SUDO_UID are not trusted.
Dependency injection is for trusted in-process callers and tests, not a sandbox
against arbitrary code already running in the privileged process.

On a disposable host with Checkmk already installed, the preparatory command is:

```bash
sudo /opt/dwlab/venv/bin/python -m dwlabcmkapi.credential_bootstrap \
  prepare-new-site --site example --site-uid 6000 --site-gid 6000
```

**Do not run this for an existing customer site or start the resulting site.**
The command intentionally stops at `awaiting-accounts`, with
`activation_allowed=false`. It does not yet create dwlabcmkadm or an automation
account, verify their access, disable cmkadmin, or activate web services. Those
operations and deployment integration are the next increment. LDAP integration
is separate follow-up work. CMK-01 remains open until the complete workflow and
artifact/runtime confidentiality checks pass.

### Credential And Process Boundaries

- The target generates three independent 256-bit secrets: temporary cmkadmin
  bootstrap password, reserved dwlabcmkadm emergency password, and reserved
  dwlab-automation secret. Reserved accounts are not yet created.
- State lives in
  `/var/lib/dwlab/dwlabcmkapi/credentials/<site>/credentials.json`, mode 0600,
  in OS-owned 0700 directories. It is persistent recovery state, not general
  installation YAML or a deployment artifact. Root is the production owner.
- State is validated, exclusively locked per site, atomically replaced and
  fsynced. Existing links, hardlinks, unsafe ownership/modes and malformed state
  are rejected rather than silently repaired. Existing credentials never rotate
  just because preparation is invoked again.
- OMD creates a stopped site with `--no-autostart`. Its internally generated
  initial password is not parsed or stored: stdout and stderr are discarded.
  Our target-generated temporary password is then set with the supported
  `cmk-passwd --stdin cmkadmin` command in the site's login environment.
  Passwords are never command arguments, Docker environment variables or logs.
- The native adapter currently accepts the Checkmk 2.4/2.5 release lines only.
  It uses `/usr/bin/omd` and `/usr/sbin/runuser` (util-linux), requires an
  existing Checkmk installation, and never installs OS packages. Native command
  output is suppressed even on failure because it can contain secrets. Errors
  report the operation and exit status, not the suppressed output.
- Preparation never starts services, adopts existing sites, or rotates existing
  customer credentials. AUTOSTART remains off. This does not prevent an OS
  administrator from bypassing the workflow and manually forcing a site start.

OMD's native stdin interface was verified against official Checkmk source:
[2.4 cmk-passwd](https://github.com/Checkmk/checkmk/blob/2.4.0/cmk/cmkpasswd.py),
[2.5 cmk-passwd](https://github.com/Checkmk/checkmk/blob/2.5.0/cmk/cmkpasswd.py),
and [OMD creation/status semantics](https://github.com/Checkmk/checkmk/blob/2.4.0/omd/packages/omd/omdlib/main.py).

### Retry, Upgrade And Removal

New-site states advance from `prepared` to `creating`, `created` and
`awaiting-accounts`. Failure while creating a site leaves `creating` and requires
manual review: retry will not blindly adopt a partly created site. A failed
password-setting step can resume from `created` with the same saved material,
provided the site still exists and is stopped. A completed preparation is
idempotent; missing sites or changed UID/GID fail closed. There is no automatic
site recreation, credential regeneration or failed-site deletion.

Package upgrades do not run this command. Existing deployments remain on their
current behavior until explicitly migrated by the later integration increment.
Back up this private state as sensitive credential material. Do not delete it
after a failed attempt or remove the bootstrap password until replacement
accounts have been provisioned and verified. Future finalization must remove
the temporary password from persistent state; that transition is not implemented
yet. Package removal must not delete site state or private credential backups.

CLI output contains only site, phase, credential-file path and activation status;
operational milestones use explicit UTC timestamps. No credential retrieval
command is provided in this increment. Authorized root administrators can access
the private file, but must not paste it into tickets, logs or public terminals.

Standalone tests use temporary directories and fake native command runners:

```bash
python3 -m pytest -q tests/test_credential_bootstrap.py
```

They test authorization, per-site independence, privacy, safe retries and failure
states without creating real sites. Native Checkmk/VM bootstrap acceptance is
still required before integrating this into customer deployment.

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
