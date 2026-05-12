from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="SEO_BHISHMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"

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
