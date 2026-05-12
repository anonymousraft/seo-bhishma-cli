from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="SEO_BHISHMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider (auto-detected from API keys when unset)
    llm_provider: str = ""
    llm_model: str = ""

    # API keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Google Search Console
    gsc_credentials_path: str = ""
    gsc_token_path: str = "token.pickle"

    # Captcha
    captcha_service: str = ""
    captcha_api_key: str = ""

    # NLP
    spacy_model: str = "en_core_web_sm"

    # Logging
    log_level: str = "INFO"

    def resolve_provider(self) -> str:
        """Pick a provider in this order: explicit ``llm_provider`` → OpenAI key → Anthropic key.

        Returns ``""`` if no provider is configured.
        """
        if self.llm_provider:
            return self.llm_provider.lower()
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        return ""

    def resolve_model(self, provider: str | None = None) -> str:
        """Pick a model: explicit ``llm_model`` overrides; otherwise per-provider default."""
        if self.llm_model:
            return self.llm_model
        provider = (provider or self.resolve_provider()).lower()
        if provider == "anthropic":
            return DEFAULT_ANTHROPIC_MODEL
        return DEFAULT_OPENAI_MODEL
