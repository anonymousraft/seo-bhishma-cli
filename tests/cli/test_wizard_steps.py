"""Tests for the interactive first-run wizard.

Each wizard section is tested by monkey-patching ``rich.prompt.Prompt.ask`` and
``rich.prompt.Confirm.ask`` so we can script the answer flow deterministically.
Live API calls are mocked at the validator boundary.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from seo_bhishma.agents.validators import ValidationResult, ValidationStatus
from seo_bhishma.cli import wizard as wizard_module
from seo_bhishma.cli.user_config import UserConfig


@pytest.fixture(autouse=True)
def _sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SEO_BHISHMA_HOME", str(tmp_path))
    return tmp_path


class _ScriptedPrompts:
    """Replay a sequence of answers to ``Prompt.ask`` / ``Confirm.ask`` calls."""

    def __init__(self, answers: list[Any]) -> None:
        self._iter: Iterator[Any] = iter(answers)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        prompt = args[0] if args else kwargs.get("prompt", "")
        self.calls.append((str(prompt), kwargs))
        try:
            return next(self._iter)
        except StopIteration as exc:  # pragma: no cover - test bug
            raise AssertionError(
                f"Wizard asked more questions than expected: {prompt!r}"
            ) from exc


def _patch_prompts(monkeypatch: pytest.MonkeyPatch, *, prompt: list[Any], confirm: list[bool]):
    """Patch both Prompt.ask and Confirm.ask with two independent scripts."""
    prompt_script = _ScriptedPrompts(prompt)
    confirm_script = _ScriptedPrompts(confirm)
    monkeypatch.setattr("seo_bhishma.cli.wizard.Prompt.ask", prompt_script)
    monkeypatch.setattr("seo_bhishma.cli.wizard.Confirm.ask", confirm_script)
    return prompt_script, confirm_script


# ---------------------------------------------------------------------------
# Section 1 — interface preference
# ---------------------------------------------------------------------------


def test_section_interface_picks_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=["menu"], confirm=[])
    result = wizard_module._section_interface(UserConfig(), step=1)
    assert result.default_interface == "menu"


def test_section_interface_keeps_chat_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=["chat"], confirm=[])
    result = wizard_module._section_interface(UserConfig(), step=1)
    assert result.default_interface == "chat"


# ---------------------------------------------------------------------------
# Section 2 — LLM provider
# ---------------------------------------------------------------------------


def test_section_llm_skip_keeps_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=["skip"], confirm=[])
    starting = UserConfig(openai_api_key="sk-existing")
    result = wizard_module._section_llm_provider(starting, step=2)
    assert result.openai_api_key == "sk-existing"
    assert result.llm_provider == ""


def test_section_llm_openai_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # answers: provider="openai" -> key="sk-good" -> no model override (blank)
    _patch_prompts(monkeypatch, prompt=["openai", "sk-good", ""], confirm=[])
    with patch.object(
        wizard_module,
        "validate_openai_key",
        return_value=ValidationResult(ValidationStatus.OK),
    ) as mock:
        result = wizard_module._section_llm_provider(UserConfig(), step=2)
    assert result.openai_api_key == "sk-good"
    assert result.llm_provider == "openai"
    assert result.llm_model == ""
    mock.assert_called_once_with("sk-good")


def test_section_llm_invalid_key_then_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    # answers: provider="openai" -> "sk-bad" (rejected) -> retry yes ->
    #          "sk-good" (accepted) -> model override blank
    _patch_prompts(
        monkeypatch,
        prompt=["openai", "sk-bad", "sk-good", ""],
        confirm=[True],  # "Try a different key?"
    )
    validator_results = iter(
        [
            ValidationResult(ValidationStatus.UNAUTHORIZED, "bad key"),
            ValidationResult(ValidationStatus.OK),
        ]
    )
    with patch.object(
        wizard_module,
        "validate_openai_key",
        side_effect=lambda key: next(validator_results),
    ):
        result = wizard_module._section_llm_provider(UserConfig(), step=2)
    assert result.openai_api_key == "sk-good"


def test_section_llm_invalid_key_no_retry_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(
        monkeypatch,
        prompt=["openai", "sk-bad", ""],
        confirm=[False],  # "Try a different key?" -> no
    )
    with patch.object(
        wizard_module,
        "validate_openai_key",
        return_value=ValidationResult(ValidationStatus.UNAUTHORIZED, "bad"),
    ):
        result = wizard_module._section_llm_provider(UserConfig(), step=2)
    assert result.openai_api_key == ""


def test_section_llm_network_error_offers_save_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_prompts(
        monkeypatch,
        prompt=["openai", "sk-unverified", ""],
        confirm=[True],  # "Save the key anyway and validate later?" -> yes
    )
    with patch.object(
        wizard_module,
        "validate_openai_key",
        return_value=ValidationResult(ValidationStatus.NETWORK, "DNS error"),
    ):
        result = wizard_module._section_llm_provider(UserConfig(), step=2)
    assert result.openai_api_key == "sk-unverified"


def test_section_llm_both_providers_asks_for_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # answers: "both", "sk-openai" (ok), "sk-ant" (ok), default="anthropic", model blank
    _patch_prompts(
        monkeypatch,
        prompt=["both", "sk-openai", "sk-ant", "anthropic", ""],
        confirm=[],
    )
    with patch.object(
        wizard_module,
        "validate_openai_key",
        return_value=ValidationResult(ValidationStatus.OK),
    ), patch.object(
        wizard_module,
        "validate_anthropic_key",
        return_value=ValidationResult(ValidationStatus.OK),
    ):
        result = wizard_module._section_llm_provider(UserConfig(), step=2)
    assert result.openai_api_key == "sk-openai"
    assert result.anthropic_api_key == "sk-ant"
    assert result.llm_provider == "anthropic"


def test_section_llm_empty_key_skips_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing Enter at the key prompt skips that provider gracefully."""
    _patch_prompts(monkeypatch, prompt=["openai", "", ""], confirm=[])
    with patch.object(wizard_module, "validate_openai_key") as mock:
        result = wizard_module._section_llm_provider(UserConfig(), step=2)
    mock.assert_not_called()  # never validated because no key was entered
    assert result.openai_api_key == ""


# ---------------------------------------------------------------------------
# Section 3 — GSC
# ---------------------------------------------------------------------------


def test_section_gsc_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=[], confirm=[False])
    result = wizard_module._section_gsc(UserConfig(), step=3)
    assert result.gsc_credentials_path == ""


def test_section_gsc_accepts_valid_creds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    creds = tmp_path / "creds.json"
    creds.write_text(json.dumps({"installed": {"client_id": "abc"}}), encoding="utf-8")
    _patch_prompts(monkeypatch, prompt=[str(creds)], confirm=[True])
    result = wizard_module._section_gsc(UserConfig(), step=3)
    assert result.gsc_credentials_path == str(creds)


def test_section_gsc_retries_on_bad_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    good = tmp_path / "creds.json"
    good.write_text(json.dumps({"installed": {"client_id": "abc"}}), encoding="utf-8")
    # answers: bad path, then a good one. confirms: configure=yes, retry=yes
    _patch_prompts(
        monkeypatch,
        prompt=["/nonexistent/file.json", str(good)],
        confirm=[True, True],
    )
    result = wizard_module._section_gsc(UserConfig(), step=3)
    assert result.gsc_credentials_path == str(good)


# ---------------------------------------------------------------------------
# Section 4 — CAPTCHA
# ---------------------------------------------------------------------------


def test_section_captcha_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=[], confirm=[False])
    result = wizard_module._section_captcha(UserConfig(), step=4)
    assert result.captcha_service == ""


def test_section_captcha_saves_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # confirm=[True] to configure, prompts: service="2captcha", key
    _patch_prompts(monkeypatch, prompt=["2captcha", "cap-key-123"], confirm=[True])
    result = wizard_module._section_captcha(UserConfig(), step=4)
    assert result.captcha_service == "2captcha"
    assert result.captcha_api_key == "cap-key-123"


# ---------------------------------------------------------------------------
# Section 5 — Advanced
# ---------------------------------------------------------------------------


def test_section_advanced_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=[], confirm=[False])
    starting = UserConfig(spacy_model="en_core_web_sm", log_level="INFO")
    result = wizard_module._section_advanced(starting, step=5)
    assert result.spacy_model == "en_core_web_sm"
    assert result.log_level == "INFO"


def test_section_advanced_sets_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(monkeypatch, prompt=["en_core_web_lg", "DEBUG"], confirm=[True])
    result = wizard_module._section_advanced(UserConfig(), step=5)
    assert result.spacy_model == "en_core_web_lg"
    assert result.log_level == "DEBUG"


# ---------------------------------------------------------------------------
# Full wizard end-to-end
# ---------------------------------------------------------------------------


def test_run_wizard_saves_complete_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drive every section and verify the saved YAML has every value."""
    _patch_prompts(
        monkeypatch,
        prompt=[
            "chat",            # section 1 - interface
            "openai",          # section 2 - which provider
            "sk-ok",           # section 2 - openai key
            "gpt-4o",          # section 2 - model override
            # section 3 GSC declined via confirm=False
            "2captcha",        # section 4 - service
            "cap-key",         # section 4 - api key
            "en_core_web_sm",  # section 5 - spacy model
            "DEBUG",           # section 5 - log level
        ],
        confirm=[
            False,  # section 3 - "Configure Search Console?" -> no
            True,   # section 4 - "Configure CAPTCHA service?" -> yes
            True,   # section 5 - "Configure advanced settings?" -> yes
            True,   # final - "Save and continue?"
        ],
    )
    with patch.object(
        wizard_module,
        "validate_openai_key",
        return_value=ValidationResult(ValidationStatus.OK),
    ):
        saved = wizard_module.run_wizard()
    assert saved.default_interface == "chat"
    assert saved.openai_api_key == "sk-ok"
    assert saved.llm_provider == "openai"
    assert saved.llm_model == "gpt-4o"
    assert saved.gsc_credentials_path == ""
    assert saved.captcha_service == "2captcha"
    assert saved.captcha_api_key == "cap-key"
    assert saved.log_level == "DEBUG"

    # And the same config was persisted.
    from seo_bhishma.cli.user_config import load_config

    reloaded = load_config()
    assert reloaded is not None
    assert reloaded.model_dump() == saved.model_dump()


def test_run_wizard_consumes_legacy_preferences_on_upgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On upgrade from the pre-wizard CLI, the legacy preferences.yaml's
    ``default_interface`` becomes the default for section 1 and the legacy file is removed.
    """
    import yaml

    from seo_bhishma.cli.user_config import legacy_preferences_path

    legacy = legacy_preferences_path()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(yaml.safe_dump({"default_interface": "menu"}), encoding="utf-8")

    captured_default: dict[str, str] = {}

    def fake_prompt_ask(prompt: str, **kwargs):
        # Section 1 asks for the interface; record the offered default and accept it.
        if "Default interface" in prompt:
            captured_default["interface_default"] = kwargs.get("default", "")
            return kwargs.get("default", "chat")
        return "skip"  # LLM section choice

    monkeypatch.setattr("seo_bhishma.cli.wizard.Prompt.ask", fake_prompt_ask)
    monkeypatch.setattr(
        "seo_bhishma.cli.wizard.Confirm.ask",
        _ScriptedPrompts([False, False, False, True]),  # GSC, CAPTCHA, advanced, save
    )

    saved = wizard_module.run_wizard()

    assert captured_default["interface_default"] == "menu"
    assert saved.default_interface == "menu"
    assert not legacy.exists(), "legacy preferences.yaml must be removed by the wizard"


def test_run_wizard_declines_save_does_not_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_prompts(
        monkeypatch,
        prompt=["chat", "skip"],
        confirm=[False, False, False, False],  # decline all sections + don't save
    )
    saved = wizard_module.run_wizard()
    from seo_bhishma.cli.user_config import load_config, user_config_path

    assert not user_config_path().exists()
    # The returned state still reflects the answers (chat default), it just wasn't persisted.
    assert saved.default_interface == "chat"
    assert load_config() is None
