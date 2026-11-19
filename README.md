# dwlabcmkapi

`dwlabcmkapi` provides a simple and extensible Python interface to interact with Checkmk servers, manage monitoring configurations, schedule backups, and integrate Checkmk operations into your custom workflows.

## Scoped Bootstrap Activation (0.26.0)

Account provisioning supports native Checkmk 2.4 and 2.5 registration APIs.
Before starting, clear existing pending configuration changes and disable
remote configuration/user replication. Provisioning refuses unrelated pending
work; it records only the acknowledged account changes in a root-private
ledger. An ambiguous mutation interrupted before its checkpoint requires manual
review, not automatic adoption of pending work.

After account completion, start the site and finalize its recorded changes:

```bash
sudo omd start YOUR_SITE
sudo /opt/dwlab/venv/bin/python -m dwlabcmkapi.account_activation \
  complete --site YOUR_SITE
```

The finalizer pins the pending-change ETag and the local site. Emergency
authorization may activate only the exact recorded bootstrap batch, never
unrelated administrator changes. A persisted activation UUID permits polling
retries without submitting another batch. Successful per-site activation is
required before ordinary credential consumers can use the new reference.
Completed retries do not activate later customer work. Normal catalog operations
retain `force_foreign_changes=False`.

Deployment must stop the site if finalization fails. The portable container
bootstrap starts and stops the site for this finalization only after account
proofs, before announcing its VPN. Existing prepared 0.25 states with unrecorded
pending changes need manual review. Do not downgrade the core reader after
writing the extended private state; restore matching code and state together.

## Container Restart Safety (0.25.1)

The existing-volume entrypoint receives only its validated, non-secret site ID
in addition to the fixed subprocess environment. Credential values are never
environment variables. Missing native site configuration blocks startup before
the vendor entrypoint can accidentally recreate a damaged site. Consumers of
the portable container bootstrap must use at least 0.25.1.

## Private Credential References (0.25.0)

Both `load_central_server_config` and `RestAPIcredentials.fromFile` accept
`cmkCredentialsFile` in installation settings. The value is an absolute reference
to this site's target-generated private state, for example:

```yaml
cmkSite: central
cmkCredentialsFile: /var/lib/dwlab/dwlabcmkapi/credentials/central/credentials.json
```

The reference contains no password. Resolving it requires OS root, mode 0700
credential directories, a singly linked mode 0600 file, trusted directory
ancestry, `accounts-ready` state and verified bootstrap activation. Only the automation identity is returned;
the emergency password is not used by ordinary API consumers. Missing, unsafe,
incomplete or mismatched references fail closed, even if old password settings
are also present. Existing HTTPS identity and loopback routing policies remain
unchanged.

For a reviewed upgrade, complete the existing site's credential migration before
adding the reference. Do not point at another site's state or copy credential
files into a release bundle. Legacy `cmkadmin_username`/`cmkadmin_password` remain
temporarily readable when no reference is configured, with a migration warning.
This compatibility path does not perform migration or rotate existing accounts.
Removing the reference deliberately re-enables that compatibility path; remove
retired plaintext settings as part of the reviewed migration, not beforehand.

### Explicit Existing-Site Migration

Stop the site during an approved maintenance window. Keep a VM/system recovery
snapshot as well. The independent core adapter never starts services itself:

```bash
sudo /opt/dwlab/venv/bin/python -m dwlabcmkapi.site_installation \
  migrate-existing-site \
  --settings /opt/dwlab/dwlab-cmkcentralserver/etc/dw-lab_InstallationSettings.yaml \
  --approve-existing-site
```

The settings file must be root-owned, singly linked and mode 0600. The old
password is read in memory, not accepted as an argument or environment variable.
Existing replacement users or a matching role are refused before migration
intent is recorded. The original password must authenticate; migration does not
reset it to gain access. A private `before-migration.tar.gz` preserves site `etc`
and `var/check_mk/web` before account changes. This is an account-configuration
recovery backup, not a complete monitoring-data/system backup. Symlinks remain
links, existing archives are never overwritten, and backup failure blocks all
account mutation. Interrupted backup creation requires manual review.

Successful account completion publishes the credential reference, removes old
password/username keys and preserves a private `settings.before-bootstrap.yaml`.
The original settings and backup can contain retired passwords: protect them as
secrets. Concurrent settings changes are refused rather than overwritten. A
failed migration retains private recovery state and leaves activation blocked.
Successful retries verify accounts again, without rotating credentials. Do not
roll back only the YAML after retiring the old account: restore site account
configuration and its private credential state consistently.

For a new stopped site, use `provision-new-site --settings FILE` instead. The
existing-site approval flag is not an automatic adoption or migration switch
for ordinary package installation.

### Restricted Automation Role

Starting with 0.25.0, new account completion creates `dwlab_automation`, based on
Checkmk's `user` role, explicitly disabling target-registered permissions outside
the reviewed host/site/activation allowlist. `dwlabcmkadm` remains the emergency
administrator. It performs bootstrap retirement; the machine account no longer
needs user or role administration. Every verification independently authenticates
the machine account and checks that user-management access is rejected.
Permission expansion fails verification instead of silently being accepted.

Existing 0.24.0 prepared/completed accounts with an admin automation role require
review; they are not silently converted by an upgrade. Historical documentation
below describes the 0.24.0 foundation, not the new restricted-role contract.

This core release does not by itself rewire existing deployment scripts or
generated customer packages. Deployment integration and VM acceptance remain
necessary before closing CMK-01.

### Container And Agent Adapters

`PortableBootstrapBundle` exports exact, checksummed core bootstrap sources under
an isolated namespace for generated Docker contexts. It contains no settings or
credentials and does not require pip/wheels inside the Checkmk image. Persistent
target-generated state must be mounted privately; it must never enter an image
layer. `ContainerSiteBootstrap` verifies credentials before enabling autostart.
The caller must not start VPN/HTTP services before this gate succeeds. The native
site data-plane listener uses container port 5000; published ports, VPN routing
and firewall restrictions remain deployment-owned policies.

Existing legacy containers require explicit `container_migration prepare --site
SITE --credential-root ROOT --approve-existing-site` before replacement. Use an
installed 0.25.0 runtime and an approved recovery snapshot. This stops the old
site and privately backs up its account configuration; it reads the old password
from the local Docker daemon in memory without echoing inspect output. It does
not retire accounts itself. A failed backup leaves the old container available
for recovery but its site may be stopped: review before restarting or retrying.
The later container bootstrap must verify replacements before retiring old access.
The `check` operation is the pre-removal guard. Existing state/archives are not
overwritten. Historical `.netrc`, packages, logs and recovery copies can contain
retired passwords; their private retention/removal requires installation review.

`python -m dwlabcmkapi.agent_download --site SITE --credential-file FILE --port
8080 --destination DIR` uses only literal loopback HTTP, with environment proxy
and netrc handling disabled. Authentication stays in memory, redirects are
rejected, readiness waiting is bounded and uses a monotonic clock, filenames and
download sizes are restricted, and incomplete downloads are not published.
This is a target-local adapter, not permission for unencrypted remote APIs.

## Replacement Accounts And Bootstrap Retirement (0.24.0)

The independent core can now complete account provisioning on a new site
prepared by the 0.23.0 foundation. It remains opt-in: existing installations,
central/client deployment scripts and customer release bundles are not changed
automatically. **CMK-01 remains open until deployment integration and complete
fresh-install/upgrade acceptance have passed.**

After `prepare-new-site` returns `awaiting-accounts`, run on the same stopped site:

```bash
sudo /opt/dwlab/venv/bin/python -m dwlabcmkapi.account_bootstrap \
  complete-accounts --site example --run-id my-installation-run
```

Use the same `--credential-root` for both commands if overriding the default.
`SiteAccountCompletion` is the shared root-authorized application service behind
the CLI and Python API. It checks the site's existence, stopped status, recorded
UID/GID and supported native version. It never starts services, enables autostart,
changes firewall rules or opens a bootstrap listener.

### Authenticated Provisioning Without A Listener

The native adapter runs Checkmk's own WSGI application as the site's OS user.
It sends real authenticated REST requests to Checkmk's versioned user-management
endpoints in process, rather than opening a TCP socket or editing users.mk and
htpasswd directly. It does not inject REMOTE_USER, trust identity headers, bypass
authentication or retain login cookies between credential proofs. The WSGI base
URL is request metadata, not a remote HTTPS connection or disabled TLS check.
The supported site release lines are 2.4/2.5; the vendor-specific WSGI factory and
plugin initialization are version-scoped adapter details, not a stable public
Checkmk SDK. Revalidate the native adapter when upgrading Checkmk.

Secrets travel to site Python only through a stdin pipe, never arguments or
environment variables. The installed helper code is passed from this wheel;
site Python does not need DW-Lab packages or another source checkout. Native
stdout is reduced to status, ETag and explicitly selected non-secret account
attributes. Error bodies, exceptions and stderr are not forwarded into ordinary
DW-Lab logs. Checkmk remains the authentication and authorization owner; this
does not introduce a DW-Lab login service or separate user registry.

### Account And Recovery Contract

- `dwlabcmkadm` is a local Checkmk emergency administrator, with its own site's
  generated password and normal interactive-password authentication.
- `dwlab-automation` is a separate per-site machine account with an automation
  secret. Checkmk's extra plaintext automation-secret copy is disabled; the
  independently protected DW-Lab credential record retains the caller secret.
- Both accounts currently receive Checkmk's `admin` role, explicitly matching
  the administrative bootstrap/user-retirement operations and current broad
  site-management contract. This is not an OS root grant or a claim of a narrowed
  catalog-only role. Operational role refinement is a prerequisite to production
  rollout, alongside deployment integration. LDAP users and role mappings remain
  separate follow-up work.
- Before recording mutation intent, unexpected existing replacement accounts
  are refused. A retry may reuse an account only after authenticating with its
  already-recorded secret and verifying its expected role/authentication mode;
  mismatches are not repaired by overwriting customer accounts or passwords.
- The durable phases are `provisioning-accounts`, `retiring-bootstrap` and
  `accounts-ready`. Both replacements must independently authenticate with
  administrative API access before retirement proceeds.
- Retirement uses the automation identity and Checkmk's ETag/If-Match contract
  to disable cmkadmin and remove its password authentication. The service checks
  the disabled state and proves the old bootstrap credential receives 401/403.
  Only then is the bootstrap-password field removed from credentials.json.
- If a command fails after retirement but before saving final state, the next
  invocation uses the permanent accounts to finish safely. It does not need a
  working bootstrap account. Successful retries in accounts-ready are read-only.
  Failed completion retains private recovery material and never activates a site.

The result reports `credential_gate_passed=true` and `activation_performed=false`.
This proves credential readiness at invocation time, not TLS/network readiness
or permission to bypass subsequent installation checks. Activation integration
must call this verification service and check success, not trust a persisted
`accounts-ready` string by itself. AUTOSTART remains off until a later explicitly
approved activation workflow. OS root can still bypass the workflow manually.

The format retains schema version 1 with new phases; older core versions fail
closed on those phases. Do not downgrade a completed site to the preparatory
0.23.0 implementation. Back up private state and site configuration together.
Package upgrades/removal never invoke provisioning or delete credential state.

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
The preparation command intentionally stops at `awaiting-accounts`, with
`activation_allowed=false`. Use the separate 0.24.0 completion operation above
to provision and verify replacement accounts and retire cmkadmin. Neither
command activates web services. Deployment and LDAP integration remain follow-up
work. CMK-01 remains open until the complete workflow and artifact/runtime
confidentiality checks pass.

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
the temporary password from persistent state; 0.24.0 implements this transition
only after replacement-account and bootstrap-denial proofs. Package removal must
not delete site state or private credential backups.

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
