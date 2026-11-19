"""Resolve target-local automation credentials without copying secrets to YAML."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .credential_bootstrap import BootstrapAuthorization


class CredentialSettings(Protocol):
    """Minimal settings interface shared by installation adapters."""

    def get_variable(self, variableName: str) -> object: ...


@dataclass(frozen=True, repr=False)
class AutomationCredential:
    """In-memory authentication material; never include it in diagnostics."""

    username: str
    secret: str


class SiteAutomationCredentialProvider:
    """Read only completed, private site state using the OS root identity."""

    def __init__(self, authorization: BootstrapAuthorization | None = None) -> None:
        from .credential_bootstrap import RootBootstrapAuthorization

        self._authorization = authorization or RootBootstrapAuthorization()

    def resolve(self, credential_file: str | Path, site: str) -> AutomationCredential:
        """Reject mismatched references, symlinks, unsafe modes and pending state."""
        from .credential_bootstrap import BootstrapError

        result = self.find_ready(credential_file, site)
        if result is None:
            raise BootstrapError("Site automation credentials are not ready.")
        return result

    def find_ready(self, credential_file: str | Path, site: str) -> AutomationCredential | None:
        """Return None only for absent/pending state, never for unsafe references."""
        from .credential_bootstrap import BootstrapError, SiteCredentialStore

        self._authorization.require_root()
        path = Path(credential_file)
        if (not path.is_absolute() or ".." in path.parts
                or path.name != "credentials.json" or path.parent.name != site):
            raise BootstrapError("Credential reference must identify this site's private state.")
        with SiteCredentialStore(path.parent.parent).transaction(site) as transaction:
            state = transaction.load()
            if state is None or state.phase != "accounts-ready" or not state.activation_complete:
                return None
            return AutomationCredential("dwlab-automation", state.automation_secret)


class SettingsCredentialResolver:
    """Prefer an explicit reference; retain logged legacy compatibility only."""

    def __init__(self, provider: SiteAutomationCredentialProvider | None = None,
                 logger: logging.Logger | None = None) -> None:
        self._provider = provider or SiteAutomationCredentialProvider()
        self._logger = logger or logging.getLogger(__name__)

    def resolve(self, settings: CredentialSettings, site: str) -> AutomationCredential:
        """Never downgrade to legacy authentication after a reference failure."""
        from .credential_bootstrap import BootstrapError

        reference = settings.get_variable("cmkCredentialsFile")
        if reference is not None and reference != "":
            if not isinstance(reference, str):
                raise BootstrapError("cmkCredentialsFile must be an absolute filename.")
            return self._provider.resolve(reference, site)
        username = settings.get_variable("cmkadmin_username") or "cmkadmin"
        secret = settings.get_variable("cmkadmin_password")
        if (not isinstance(username, str) or not isinstance(secret, str) or not secret
                or any(character in username + secret for character in "\r\n\x00")):
            raise BootstrapError("Configure private site credentials or explicitly migrate legacy authentication.")
        self._logger.warning(
            "Legacy Checkmk credential settings in use; reviewed account migration is required."
        )
        return AutomationCredential(username, secret)
