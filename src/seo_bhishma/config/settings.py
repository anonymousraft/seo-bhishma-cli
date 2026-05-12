from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"


class Settings(BaseSettings):
    """Application settings, layered (highest priority first):

    1. Init kwargs (e.g. ``Settings(openai_api_key="sk-...")``).
    2. ``SEO_BHISHMA_*`` environment variables.
    3. A local ``.env`` file in the working directory.
    4. The user's saved configuration written by the first-run wizard
       (``~/.config/seo-bhishma/config.yaml`` / ``%APPDATA%\\seo-bhishma\\config.yaml``).
    5. Hard-coded defaults below.

    This keeps CI / one-shot env-var overrides working while still picking up
    whatever the user set through ``seo-bhishma config`` for normal use.
    """

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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Layer the user's saved YAML config below env vars but above defaults."""
        # Imported lazily so this module stays usable when the CLI tree isn't installed.
        from seo_bhishma.cli.user_config import user_config_path

        yaml_path = user_config_path()
        yaml_source: PydanticBaseSettingsSource | None = None
        if yaml_path.exists():
            yaml_source = YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path)

        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if yaml_source is not None:
            sources.append(yaml_source)
        sources.append(file_secret_settings)
        return tuple(sources)

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
