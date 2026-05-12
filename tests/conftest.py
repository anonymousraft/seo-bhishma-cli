import pytest

from seo_bhishma.config.settings import Settings


@pytest.fixture
def settings():
    """Provide a Settings instance with test defaults."""
    return Settings(
        openai_api_key="test-key",
        anthropic_api_key="test-key",
        llm_provider="openai",
        llm_model="gpt-4o",
        log_level="DEBUG",
    )
