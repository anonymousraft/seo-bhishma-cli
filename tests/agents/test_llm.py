"""Tests for the LLM provider abstraction."""

from __future__ import annotations

import pytest

from seo_bhishma.agents.llm import LlmConfigError, get_llm
from seo_bhishma.config.settings import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    Settings,
)


def test_no_provider_no_keys_raises() -> None:
    s = Settings(llm_provider="", llm_model="", openai_api_key="", anthropic_api_key="")
    assert s.resolve_provider() == ""
    with pytest.raises(LlmConfigError):
        get_llm(s)


def test_openai_key_autodetects_openai() -> None:
    s = Settings(llm_provider="", openai_api_key="sk-test")
    assert s.resolve_provider() == "openai"
    assert s.resolve_model() == DEFAULT_OPENAI_MODEL


def test_anthropic_key_autodetects_anthropic() -> None:
    s = Settings(llm_provider="", openai_api_key="", anthropic_api_key="sk-ant-test")
    assert s.resolve_provider() == "anthropic"
    assert s.resolve_model() == DEFAULT_ANTHROPIC_MODEL


def test_openai_key_wins_over_anthropic_when_both_set() -> None:
    s = Settings(llm_provider="", openai_api_key="sk-1", anthropic_api_key="sk-2")
    assert s.resolve_provider() == "openai"


def test_explicit_provider_overrides_autodetect() -> None:
    s = Settings(llm_provider="anthropic", openai_api_key="sk-1", anthropic_api_key="sk-2")
    assert s.resolve_provider() == "anthropic"


def test_explicit_model_overrides_default() -> None:
    s = Settings(llm_provider="openai", llm_model="gpt-4o", openai_api_key="sk-test")
    assert s.resolve_model() == "gpt-4o"


def test_provider_set_but_no_key_raises() -> None:
    s = Settings(llm_provider="openai", openai_api_key="", anthropic_api_key="sk-ant")
    with pytest.raises(LlmConfigError, match="OPENAI_API_KEY"):
        get_llm(s)


def test_unknown_provider_raises() -> None:
    s = Settings(llm_provider="cohere", openai_api_key="sk-test")
    with pytest.raises(LlmConfigError, match="Unknown llm_provider"):
        get_llm(s)
