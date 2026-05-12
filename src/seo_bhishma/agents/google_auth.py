"""Google OAuth helper for Search Console — one-click login, JSON token storage.

Design choices:

* The OAuth client config is bundled with the package (``data/oauth_client.json``)
  so users don't need to create a Google Cloud project. Per Google's OAuth 2.0
  spec for installed apps, ``client_id`` is not confidential; we additionally
  rely on PKCE (RFC 7636, enabled by default in ``google-auth-oauthlib``) so
  no client_secret is needed.

* The user can override the bundled client by setting
  ``SEO_BHISHMA_GSC_CREDENTIALS_PATH`` (or storing it in ``config.yaml`` via
  the wizard). Use case: a Workspace org that requires its own OAuth client.

* Tokens are stored as JSON at ``<user_config_dir>/gsc_token.json`` instead of
  pickle. JSON is cross-version-safe, inspectable, and avoids pickle security
  caveats.

* The legacy working-directory ``token.pickle`` from earlier releases is
  imported on first run.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import stat
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from seo_bhishma.config.settings import Settings

if TYPE_CHECKING:  # pragma: no cover
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/webmasters",
]

_BUNDLED_OAUTH_CLIENT = ("seo_bhishma.data", "oauth_client.json")
_PLACEHOLDER_CLIENT_ID = "REPLACE_ME-PLACEHOLDER.apps.googleusercontent.com"


class GoogleAuthError(RuntimeError):
    """Raised when GSC authentication cannot be completed."""


class NoBundledClient(GoogleAuthError):
    """Raised when the bundled OAuth client still has the placeholder id."""


@dataclass(frozen=True)
class OAuthClientConfig:
    """Parsed OAuth client config (the ``installed`` block of Google's JSON)."""

    client_id: str
    client_secret: str
    auth_uri: str
    token_uri: str
    redirect_uris: list[str]
    source: str  # "bundled" | "override:<path>"

    def to_flow_config(self) -> dict:
        """Return the dict shape ``InstalledAppFlow.from_client_config`` expects."""
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": self.auth_uri,
                "token_uri": self.token_uri,
                "redirect_uris": self.redirect_uris,
            }
        }


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def gsc_token_path() -> Path:
    """Return the absolute path of the saved GSC OAuth token (JSON)."""
    # Imported lazily to break a circular import with the CLI commands package,
    # which transitively imports this module.
    from seo_bhishma.cli.user_config import _config_dir

    return _config_dir() / "gsc_token.json"


def legacy_token_path() -> Path:
    """Pre-wizard token location (working-directory pickle)."""
    return Path("token.pickle")


# ---------------------------------------------------------------------------
# OAuth client config loading
# ---------------------------------------------------------------------------


def load_client_config() -> OAuthClientConfig:
    """Resolve which OAuth client to use.

    Precedence:

    1. ``SEO_BHISHMA_GSC_CREDENTIALS_PATH`` (env or wizard config) — user's
       own OAuth client JSON downloaded from Google Cloud Console.
    2. The package-bundled ``data/oauth_client.json`` (only if its
       placeholder ``client_id`` has been replaced with a real value).

    Raises :class:`NoBundledClient` when neither is usable, with a clear
    message pointing the user at ``seo-bhishma config set
    gsc_credentials_path``.
    """
    override = Settings().gsc_credentials_path
    if override:
        path = Path(override)
        if not path.is_file():
            raise GoogleAuthError(
                f"SEO_BHISHMA_GSC_CREDENTIALS_PATH points to a missing file: {path}"
            )
        return _parse_client_json(path.read_text(encoding="utf-8"), source=f"override:{path}")

    bundled = resources.files(_BUNDLED_OAUTH_CLIENT[0]).joinpath(_BUNDLED_OAUTH_CLIENT[1])
    config = _parse_client_json(bundled.read_text(encoding="utf-8"), source="bundled")
    if config.client_id == _PLACEHOLDER_CLIENT_ID:
        raise NoBundledClient(
            "The bundled OAuth client_id is still the placeholder. Either:\n"
            "  1. (Maintainer) Register a Desktop-app OAuth client at "
            "https://console.cloud.google.com/apis/credentials, then replace "
            "the placeholder in src/seo_bhishma/data/oauth_client.json.\n"
            "  2. (User) Use your own OAuth client JSON via\n"
            "       seo-bhishma config set gsc_credentials_path /path/to/client.json"
        )
    return config


def _parse_client_json(raw: str, *, source: str) -> OAuthClientConfig:
    data = json.loads(raw)
    installed = data.get("installed") or data.get("web")
    if not isinstance(installed, dict) or "client_id" not in installed:
        raise GoogleAuthError(
            "OAuth client JSON is missing the 'installed.client_id' field."
        )
    return OAuthClientConfig(
        client_id=str(installed["client_id"]),
        client_secret=str(installed.get("client_secret", "") or ""),
        auth_uri=str(installed.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")),
        token_uri=str(installed.get("token_uri", "https://oauth2.googleapis.com/token")),
        redirect_uris=list(installed.get("redirect_uris") or ["http://localhost"]),
        source=source,
    )


# ---------------------------------------------------------------------------
# Token storage
# ---------------------------------------------------------------------------


def load_saved_credentials() -> Credentials | None:
    """Return the saved Credentials (refreshed if needed), or ``None`` if no token."""
    # Lazy import — google-auth is a base dep but importing it costs ~100ms.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = gsc_token_path()
    if not path.exists():
        # First-time read after upgrade: try to import a legacy token.pickle.
        migrated = migrate_legacy_token()
        if migrated is not None:
            return migrated
        return None

    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        creds = Credentials.from_authorized_user_info(info, SCOPES)
    except Exception as e:
        logger.error("Failed to read saved GSC token at %s: %s", path, e)
        return None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.error("GSC token refresh failed (%s). Run `seo-bhishma gsc login`.", e)
            return None
        _write_token(creds)
        return creds
    return None


def save_credentials(creds: Credentials) -> Path:
    """Persist credentials to the user config dir as JSON."""
    return _write_token(creds)


def clear_token() -> bool:
    """Delete the saved token (used by ``gsc logout``). Returns True if removed."""
    path = gsc_token_path()
    if not path.exists():
        return False
    path.unlink()
    return True


def _write_token(creds: Credentials) -> Path:
    """Atomic JSON write with chmod 0600 on POSIX."""
    path = gsc_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(creds.to_json(), encoding="utf-8")
    if not sys.platform.startswith("win"):
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    os.replace(tmp, path)
    return path


def migrate_legacy_token() -> Credentials | None:
    """Import a pre-wizard ``token.pickle`` into the new JSON location.

    Looks at the current working directory for a legacy ``token.pickle`` and,
    if found, converts it to the new JSON format and removes the old file.
    Returns the migrated ``Credentials`` or ``None``.
    """
    legacy = legacy_token_path()
    if not legacy.exists():
        return None
    try:
        with legacy.open("rb") as f:
            creds = pickle.load(f)
    except Exception as e:
        logger.error("Could not import legacy token.pickle (%s). Ignoring.", e)
        try:
            legacy.unlink()
        except OSError:
            pass
        return None

    if not hasattr(creds, "to_json"):
        logger.error("Legacy token.pickle is not a google-auth Credentials object.")
        try:
            legacy.unlink()
        except OSError:
            pass
        return None

    _write_token(creds)
    try:
        legacy.unlink()
    except OSError:
        pass
    return creds


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------


def do_oauth_login(
    *,
    no_browser: bool = False,
    open_browser: bool = True,
) -> Credentials:
    """Run the OAuth flow and persist the resulting credentials.

    Args:
        no_browser: Force device-flow (prints a URL + code instead of opening
            a browser). Use for SSH sessions or environments where the system
            browser can't be launched.
        open_browser: When ``no_browser=False``, control whether to actually
            try to open the browser. ``False`` still uses the local-server
            redirect but expects the user to copy the URL manually.

    Raises:
        GoogleAuthError: If no usable OAuth client is configured.
        Exception: If the OAuth flow itself fails (user cancels, network).
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    config = load_client_config()
    flow = InstalledAppFlow.from_client_config(config.to_flow_config(), SCOPES)

    if no_browser:
        # Device-flow style: print URL + paste-back. Works in headless shells.
        creds = _run_console_flow(flow)
    else:
        creds = flow.run_local_server(
            port=0,
            open_browser=open_browser,
            success_message="Authentication complete — you can close this tab.",
        )

    save_credentials(creds)
    return creds


def _run_console_flow(flow) -> Credentials:
    """Replacement for the deprecated ``flow.run_console()`` — manual paste-back."""
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    print()
    print("Open this URL in any browser, sign in, and paste the resulting code below:")
    print()
    print(f"    {auth_url}")
    print()
    code = input("Authorization code: ").strip()
    flow.fetch_token(code=code)
    return flow.credentials


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def get_authenticated_email(creds: Credentials) -> str | None:
    """Return the Google account email a credential authenticated with, if known."""
    # google-auth puts id_token claims here when present; otherwise None.
    info = getattr(creds, "id_token", None)
    if isinstance(info, dict):
        return info.get("email")
    return None
