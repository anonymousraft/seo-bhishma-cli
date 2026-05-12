"""Tests for the ``seo-bhishma config ...`` Click command group."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from seo_bhishma.agents.validators import ValidationResult, ValidationStatus
from seo_bhishma.cli.commands.config_cmd import config
from seo_bhishma.cli.user_config import (
    UserConfig,
    load_config,
    save_config,
    user_config_path,
)


@pytest.fixture(autouse=True)
def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SEO_BHISHMA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_show_when_no_config(runner: CliRunner) -> None:
    result = runner.invoke(config, ["show"])
    assert result.exit_code == 0
    assert "No saved configuration" in result.output


def test_show_masks_secrets(runner: CliRunner) -> None:
    save_config(UserConfig(openai_api_key="sk-totally-real-12345678", llm_model="gpt-4o"))
    result = runner.invoke(config, ["show"])
    assert result.exit_code == 0
    assert "sk-totally-real" not in result.output
    assert "gpt-4o" in result.output
    assert "…" in result.output


def test_get_returns_raw_value_for_scripting(runner: CliRunner) -> None:
    save_config(UserConfig(llm_model="gpt-4o", openai_api_key="sk-secret-1234567890"))
    result = runner.invoke(config, ["get", "llm_model"])
    assert result.exit_code == 0
    assert result.output.strip() == "gpt-4o"

    # Secrets ARE unmasked for `get` (the user can pipe them into other commands).
    result = runner.invoke(config, ["get", "openai_api_key"])
    assert result.exit_code == 0
    assert result.output.strip() == "sk-secret-1234567890"


def test_get_unknown_key_fails(runner: CliRunner) -> None:
    result = runner.invoke(config, ["get", "nope"])
    assert result.exit_code == 1
    assert "Unknown config key" in result.output


def test_set_persists_value(runner: CliRunner) -> None:
    result = runner.invoke(config, ["set", "default_interface", "menu"])
    assert result.exit_code == 0
    loaded = load_config()
    assert loaded is not None
    assert loaded.default_interface == "menu"


def test_set_rejects_invalid_default_interface(runner: CliRunner) -> None:
    result = runner.invoke(config, ["set", "default_interface", "bogus"])
    assert result.exit_code == 1
    assert "must be 'chat' or 'menu'" in result.output


def test_set_rejects_invalid_log_level(runner: CliRunner) -> None:
    result = runner.invoke(config, ["set", "log_level", "INVALID"])
    assert result.exit_code == 1
    assert "DEBUG/INFO/WARNING/ERROR" in result.output


def test_set_rejects_unknown_key(runner: CliRunner) -> None:
    result = runner.invoke(config, ["set", "fake_field", "foo"])
    assert result.exit_code == 1
    assert "Unknown config key" in result.output


def test_set_openai_api_key_validates_live(runner: CliRunner) -> None:
    """``config set openai_api_key`` should call the live validator."""
    with patch(
        "seo_bhishma.cli.commands.config_cmd.validate_openai_key",
        return_value=ValidationResult(ValidationStatus.OK),
    ) as mock:
        result = runner.invoke(config, ["set", "openai_api_key", "sk-valid"])
    assert result.exit_code == 0
    mock.assert_called_once_with("sk-valid")
    assert load_config().openai_api_key == "sk-valid"


def test_set_openai_api_key_rejects_invalid_key(runner: CliRunner) -> None:
    with patch(
        "seo_bhishma.cli.commands.config_cmd.validate_openai_key",
        return_value=ValidationResult(ValidationStatus.UNAUTHORIZED, "bad key"),
    ):
        result = runner.invoke(config, ["set", "openai_api_key", "sk-bad"])
    assert result.exit_code == 1
    assert "rejected" in result.output
    # The bad key should NOT have been persisted.
    assert load_config() is None or load_config().openai_api_key == ""


def test_set_anthropic_api_key_validates_live(runner: CliRunner) -> None:
    with patch(
        "seo_bhishma.cli.commands.config_cmd.validate_anthropic_key",
        return_value=ValidationResult(ValidationStatus.OK),
    ) as mock:
        result = runner.invoke(config, ["set", "anthropic_api_key", "sk-ant-good"])
    assert result.exit_code == 0
    mock.assert_called_once_with("sk-ant-good")


def test_path_prints_config_file_path(runner: CliRunner) -> None:
    result = runner.invoke(config, ["path"])
    assert result.exit_code == 0
    assert str(user_config_path()) in result.output


def test_reset_yes_removes_config(runner: CliRunner) -> None:
    save_config(UserConfig(default_interface="menu"))
    assert user_config_path().exists()
    result = runner.invoke(config, ["reset", "--yes"])
    assert result.exit_code == 0
    assert not user_config_path().exists()


def test_reset_without_yes_prompts_and_aborts_on_n(runner: CliRunner) -> None:
    save_config(UserConfig(default_interface="menu"))
    result = runner.invoke(config, ["reset"], input="n\n")
    assert result.exit_code == 0
    assert user_config_path().exists()
    assert "Aborted" in result.output


def test_reset_no_file_warns(runner: CliRunner) -> None:
    result = runner.invoke(config, ["reset", "--yes"])
    assert result.exit_code == 0
    assert "No config" in result.output


def test_set_then_get_roundtrip_via_yaml(runner: CliRunner) -> None:
    """`config set` writes to the same YAML that pydantic-settings will read."""
    runner.invoke(config, ["set", "llm_model", "claude-opus-4-7"])
    raw = yaml.safe_load(user_config_path().read_text(encoding="utf-8"))
    assert raw["llm_model"] == "claude-opus-4-7"
