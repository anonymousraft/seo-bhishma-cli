"""Tests for the system-wide user configuration store."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
import yaml

from seo_bhishma.cli.user_config import (
    SCHEMA_VERSION,
    SECRET_FIELDS,
    UserConfig,
    _mask_secret,
    delete_config,
    legacy_preferences_path,
    load_config,
    save_config,
    user_config_path,
)


@pytest.fixture(autouse=True)
def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Force every config write into a tmp dir for the whole test module."""
    monkeypatch.setenv("SEO_BHISHMA_HOME", str(tmp_path))
    return tmp_path


def test_load_returns_none_when_no_file_exists() -> None:
    assert load_config() is None


def test_roundtrip_preserves_all_fields() -> None:
    original = UserConfig(
        default_interface="menu",
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-5",
        openai_api_key="sk-openai-12345678901234567890",
        anthropic_api_key="sk-ant-12345678901234567890",
        gsc_credentials_path="/tmp/creds.json",
        gsc_token_path="custom-token.pickle",
        captcha_service="2captcha",
        captcha_api_key="cap-key-123",
        spacy_model="en_core_web_lg",
        log_level="DEBUG",
    )
    save_config(original)

    loaded = load_config()
    assert loaded is not None
    assert loaded.model_dump() == original.model_dump()


def test_save_writes_schema_version() -> None:
    save_config(UserConfig(default_interface="chat"))
    raw = yaml.safe_load(user_config_path().read_text(encoding="utf-8"))
    assert raw["config_version"] == SCHEMA_VERSION


def test_secret_masking_in_dict() -> None:
    config = UserConfig(
        openai_api_key="sk-test-12345678",
        anthropic_api_key="sk-ant-x" * 5,
        captcha_api_key="cap-12345",  # 9 chars => *** mask
    )
    masked = config.masked_dict()
    assert "sk-test" not in masked["openai_api_key"]
    assert "…" in masked["openai_api_key"]
    assert "…" in masked["anthropic_api_key"]
    # Short secrets are fully masked to ***
    assert masked["captcha_api_key"] == "***"


def test_mask_secret_handles_short_and_empty() -> None:
    assert _mask_secret("") == ""
    assert _mask_secret("short") == "***"
    assert _mask_secret("sk-1234567890") == "sk-1…7890"


def test_secret_fields_constant_matches_model_fields() -> None:
    """If anyone adds a new secret-looking field, this constant must be updated."""
    model_fields = set(UserConfig.model_fields.keys())
    assert SECRET_FIELDS.issubset(model_fields)


def test_delete_config_removes_file() -> None:
    save_config(UserConfig())
    assert user_config_path().exists()
    assert delete_config() is True
    assert not user_config_path().exists()
    # Second delete is a no-op.
    assert delete_config() is False


def test_legacy_preferences_migration(tmp_path: Path) -> None:
    """A pre-wizard preferences.yaml should be migrated and removed on load."""
    legacy = legacy_preferences_path()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(yaml.safe_dump({"default_interface": "menu"}), encoding="utf-8")
    assert legacy.exists()

    migrated = load_config()
    assert migrated is not None
    assert migrated.default_interface == "menu"
    assert not legacy.exists(), "legacy file should be cleaned up after migration"
    assert user_config_path().exists()


def test_corrupt_yaml_returns_none() -> None:
    user_config_path().parent.mkdir(parents=True, exist_ok=True)
    user_config_path().write_text("not: valid: yaml: :", encoding="utf-8")
    assert load_config() is None


def test_unknown_fields_in_yaml_are_silently_dropped() -> None:
    user_config_path().parent.mkdir(parents=True, exist_ok=True)
    user_config_path().write_text(
        yaml.safe_dump({"default_interface": "chat", "future_field": "value"}),
        encoding="utf-8",
    )
    loaded = load_config()
    assert loaded is not None
    assert loaded.default_interface == "chat"


def test_settings_overlay_excludes_ui_and_meta_fields() -> None:
    config = UserConfig(default_interface="menu", openai_api_key="sk-x")
    overlay = config.settings_overlay()
    assert "default_interface" not in overlay
    assert "config_version" not in overlay
    assert overlay["openai_api_key"] == "sk-x"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only chmod check")
def test_save_sets_owner_only_permissions_on_posix() -> None:
    save_config(UserConfig(openai_api_key="sk-test-1234"))
    perms = stat.S_IMODE(os.stat(user_config_path()).st_mode)
    # owner read/write only — group/other must have no bits.
    assert perms & (stat.S_IRWXG | stat.S_IRWXO) == 0
