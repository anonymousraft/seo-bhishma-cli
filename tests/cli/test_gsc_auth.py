"""Tests for the GSC OAuth flow and the ``seo-bhishma gsc`` command group."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from seo_bhishma.agents.google_auth import (
    _PLACEHOLDER_CLIENT_ID,
    NoBundledClient,
    _parse_client_json,
    clear_token,
    gsc_token_path,
    legacy_token_path,
    load_client_config,
    load_saved_credentials,
    migrate_legacy_token,
    save_credentials,
)


@pytest.fixture(autouse=True)
def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Sandbox the config + working dir for every test."""
    monkeypatch.setenv("SEO_BHISHMA_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# load_client_config
# ---------------------------------------------------------------------------


def test_load_client_config_uses_override_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user-provided OAuth JSON wins over the bundled placeholder."""
    user_json = tmp_path / "my-client.json"
    user_json.write_text(
        json.dumps(
            {"installed": {"client_id": "user-client-1234.apps.googleusercontent.com"}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SEO_BHISHMA_GSC_CREDENTIALS_PATH", str(user_json))

    config = load_client_config()
    assert config.client_id == "user-client-1234.apps.googleusercontent.com"
    assert config.source.startswith("override:")


def test_load_client_config_override_missing_file_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from seo_bhishma.agents.google_auth import GoogleAuthError

    monkeypatch.setenv("SEO_BHISHMA_GSC_CREDENTIALS_PATH", "/nonexistent/client.json")
    with pytest.raises(GoogleAuthError, match="missing file"):
        load_client_config()


def test_load_client_config_placeholder_bundled_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default state (placeholder client_id still in the bundle) must error clearly."""
    monkeypatch.delenv("SEO_BHISHMA_GSC_CREDENTIALS_PATH", raising=False)
    with pytest.raises(NoBundledClient, match="placeholder"):
        load_client_config()


def test_parse_client_json_rejects_missing_client_id() -> None:
    from seo_bhishma.agents.google_auth import GoogleAuthError

    with pytest.raises(GoogleAuthError, match="client_id"):
        _parse_client_json(json.dumps({"installed": {}}), source="test")


def test_placeholder_constant_matches_bundled_json() -> None:
    """If someone edits the bundled JSON they shouldn't drift from the sentinel."""
    from importlib import resources

    bundled = resources.files("seo_bhishma.data").joinpath("oauth_client.json")
    data = json.loads(bundled.read_text(encoding="utf-8"))
    assert data["installed"]["client_id"] == _PLACEHOLDER_CLIENT_ID, (
        "Placeholder out of sync — update _PLACEHOLDER_CLIENT_ID in google_auth.py"
    )


# ---------------------------------------------------------------------------
# Token round-trip
# ---------------------------------------------------------------------------


def _fake_creds(*, valid: bool = True, expired: bool = False) -> MagicMock:
    """Build a stand-in for ``google.oauth2.credentials.Credentials``.

    All attributes that Rich rendering / save-to-disk touches are real values
    (not MagicMock auto-children) so the credential walks through the CLI
    without ``NotRenderableError`` or ``PicklingError``.
    """
    creds = MagicMock()
    creds.valid = valid
    creds.expired = expired
    creds.refresh_token = "refresh-token-xxxx"
    creds.scopes = [
        "https://www.googleapis.com/auth/webmasters.readonly",
        "https://www.googleapis.com/auth/webmasters",
    ]
    creds.id_token = {"email": "alice@example.com"}
    creds.expiry = None  # otherwise MagicMock auto-attr; Rich can't render it
    creds.to_json = MagicMock(
        return_value=json.dumps(
            {
                "token": "access-token",
                "refresh_token": "refresh-token-xxxx",
                "client_id": "fake-client.apps.googleusercontent.com",
                "client_secret": "",
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": list(creds.scopes),
            }
        )
    )
    return creds


class _PicklableCreds:
    """A pickle-safe stand-in for ``Credentials`` — only used in the legacy-migration test."""

    def __init__(self) -> None:
        self.valid = True
        self.expired = False
        self.refresh_token = "refresh-token-xxxx"
        self.scopes = [
            "https://www.googleapis.com/auth/webmasters.readonly",
            "https://www.googleapis.com/auth/webmasters",
        ]
        self.id_token = {"email": "alice@example.com"}
        self.expiry = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "token": "access-token",
                "refresh_token": self.refresh_token,
                "client_id": "fake-client.apps.googleusercontent.com",
                "client_secret": "",
                "token_uri": "https://oauth2.googleapis.com/token",
                "scopes": list(self.scopes),
            }
        )


def test_save_and_load_credentials_roundtrip() -> None:
    creds = _fake_creds(valid=True)
    save_credentials(creds)
    assert gsc_token_path().exists()

    # Read it back — Credentials.from_authorized_user_info should accept our JSON.
    with patch(
        "google.oauth2.credentials.Credentials.from_authorized_user_info",
        return_value=_fake_creds(valid=True),
    ) as mock_from:
        loaded = load_saved_credentials()
    assert loaded is not None
    assert loaded.valid is True
    mock_from.assert_called_once()


def test_load_returns_none_when_no_token() -> None:
    assert load_saved_credentials() is None


def test_load_auto_refreshes_expired_token() -> None:
    expired = _fake_creds(valid=False, expired=True)
    save_credentials(expired)
    with patch(
        "google.oauth2.credentials.Credentials.from_authorized_user_info",
        return_value=expired,
    ), patch("google.auth.transport.requests.Request"):
        load_saved_credentials()
    expired.refresh.assert_called_once()


def test_load_returns_none_when_refresh_fails() -> None:
    expired = _fake_creds(valid=False, expired=True)
    expired.refresh = MagicMock(side_effect=RuntimeError("refresh denied"))
    save_credentials(expired)
    with patch(
        "google.oauth2.credentials.Credentials.from_authorized_user_info",
        return_value=expired,
    ):
        assert load_saved_credentials() is None


def test_clear_token_removes_file() -> None:
    save_credentials(_fake_creds())
    assert gsc_token_path().exists()
    assert clear_token() is True
    assert not gsc_token_path().exists()
    # Second call is a no-op.
    assert clear_token() is False


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------


def test_migrate_legacy_token_imports_pickle(tmp_path: Path) -> None:
    """A pre-wizard ``token.pickle`` should be imported into the new JSON location."""
    creds = _PicklableCreds()
    with legacy_token_path().open("wb") as f:
        pickle.dump(creds, f)
    assert legacy_token_path().exists()

    migrated = migrate_legacy_token()
    assert migrated is not None
    assert gsc_token_path().exists()
    assert not legacy_token_path().exists(), "legacy file should be cleaned up"


def test_migrate_legacy_token_returns_none_when_missing() -> None:
    assert migrate_legacy_token() is None


def test_migrate_legacy_token_removes_corrupt_pickle() -> None:
    legacy_token_path().write_text("not a pickle", encoding="utf-8")
    assert migrate_legacy_token() is None
    assert not legacy_token_path().exists()


# ---------------------------------------------------------------------------
# `seo-bhishma gsc` command group
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_gsc_status_when_not_connected(runner: CliRunner) -> None:
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    result = runner.invoke(gsc, ["status"])
    assert result.exit_code == 0
    assert "Not connected" in result.output


def test_gsc_status_when_connected(runner: CliRunner) -> None:
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    save_credentials(_fake_creds(valid=True))
    with patch(
        "seo_bhishma.cli.commands.gsc_cmd.load_saved_credentials",
        return_value=_fake_creds(valid=True),
    ):
        result = runner.invoke(gsc, ["status"])
    assert result.exit_code == 0
    assert "connected" in result.output


def test_gsc_logout_yes_removes_token(runner: CliRunner) -> None:
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    save_credentials(_fake_creds())
    assert gsc_token_path().exists()
    result = runner.invoke(gsc, ["logout", "--yes"])
    assert result.exit_code == 0
    assert not gsc_token_path().exists()


def test_gsc_logout_no_token(runner: CliRunner) -> None:
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    result = runner.invoke(gsc, ["logout", "--yes"])
    assert result.exit_code == 0
    assert "No saved token" in result.output


def test_gsc_login_reports_missing_oauth_client_cleanly(runner: CliRunner) -> None:
    """Default state (placeholder bundled client) shouldn't crash — give a friendly panel."""
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    # No override; bundled client still has the placeholder id.
    result = runner.invoke(gsc, ["login"])
    assert result.exit_code == 2
    assert "placeholder" in result.output.lower() or "OAuth client not configured" in result.output


def test_gsc_login_happy_path_with_override(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With an override OAuth JSON + a mocked do_oauth_login, login should save the token."""
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    client_json = tmp_path / "client.json"
    client_json.write_text(
        json.dumps(
            {"installed": {"client_id": "abc.apps.googleusercontent.com"}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SEO_BHISHMA_GSC_CREDENTIALS_PATH", str(client_json))

    with patch(
        "seo_bhishma.cli.commands.gsc_cmd.do_oauth_login",
        return_value=_fake_creds(valid=True),
    ) as mock_login:
        result = runner.invoke(gsc, ["login"])
    assert result.exit_code == 0
    mock_login.assert_called_once_with(no_browser=False)
    assert "Authorized" in result.output


def test_gsc_login_no_browser_passes_flag(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    client_json = tmp_path / "client.json"
    client_json.write_text(
        json.dumps({"installed": {"client_id": "abc.apps.googleusercontent.com"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SEO_BHISHMA_GSC_CREDENTIALS_PATH", str(client_json))

    with patch(
        "seo_bhishma.cli.commands.gsc_cmd.do_oauth_login",
        return_value=_fake_creds(),
    ) as mock_login:
        result = runner.invoke(gsc, ["login", "--no-browser"])
    assert result.exit_code == 0
    mock_login.assert_called_once_with(no_browser=True)


def test_gsc_sites_requires_login(runner: CliRunner) -> None:
    from seo_bhishma.cli.commands.gsc_cmd import gsc

    result = runner.invoke(gsc, ["sites"])
    assert result.exit_code == 2
    assert "Not connected" in result.output


# ---------------------------------------------------------------------------
# core.authenticate_gsc backward-compat
# ---------------------------------------------------------------------------


def test_authenticate_gsc_raises_when_no_token() -> None:
    """The core helper should now raise AuthError pointing at `gsc login` instead of
    silently launching an OAuth browser flow."""
    from seo_bhishma.core._exceptions import AuthError
    from seo_bhishma.core.gsc_probe import authenticate_gsc

    with pytest.raises(AuthError, match="gsc login"):
        authenticate_gsc()


def test_authenticate_gsc_returns_service_when_creds_present() -> None:
    from seo_bhishma.core.gsc_probe import authenticate_gsc

    valid = _fake_creds(valid=True)
    with patch(
        "seo_bhishma.agents.google_auth.load_saved_credentials", return_value=valid
    ), patch("googleapiclient.discovery.build") as mock_build:
        mock_build.return_value = MagicMock(name="ServiceObject")
        service = authenticate_gsc()
    mock_build.assert_called_once()
    assert service is mock_build.return_value
