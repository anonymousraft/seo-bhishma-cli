"""LLM provider abstraction for the SEO Bhishma chat agent.

Resolves provider + model from :class:`seo_bhishma.config.settings.Settings`
and returns a ``BaseChatModel`` ready for tool binding. Supports OpenAI and
Anthropic; raises :class:`LlmConfigError` with a user-friendly message when no
API key is configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from seo_bhishma.config.settings import Settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


class LlmConfigError(RuntimeError):
    """Raised when no usable LLM provider can be resolved from settings."""


_HELP = (
    "No LLM provider configured. Set one of:\n"
    "  SEO_BHISHMA_OPENAI_API_KEY=sk-...\n"
    "  SEO_BHISHMA_ANTHROPIC_API_KEY=sk-ant-...\n"
    "Or set SEO_BHISHMA_LLM_PROVIDER=openai|anthropic with a matching key.\n"
    "See .env.example."
)


def get_llm(
    settings: Settings | None = None,
    *,
    model: str | None = None,
    temperature: float = 0.0,
) -> BaseChatModel:
    """Return a chat LLM picked from settings (or env), bound for tool use.

    Args:
        settings: Optional pre-built ``Settings`` instance. Defaults to ``Settings()``.
        model: Override the resolved model name (e.g. for ``/model`` slash command).
        temperature: Sampling temperature; agents default to 0.0 for tool selection.

    Raises:
        LlmConfigError: When no provider + key combination is usable.
    """
    settings = settings or Settings()
    provider = settings.resolve_provider()
    if not provider:
        raise LlmConfigError(_HELP)

    resolved_model = model or settings.resolve_model(provider)

    if provider == "openai":
        if not settings.openai_api_key:
            raise LlmConfigError(
                "llm_provider=openai but SEO_BHISHMA_OPENAI_API_KEY is empty.\n" + _HELP
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=resolved_model,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LlmConfigError(
                "llm_provider=anthropic but SEO_BHISHMA_ANTHROPIC_API_KEY is empty.\n" + _HELP
            )
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=resolved_model,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
        )

    raise LlmConfigError(
        f"Unknown llm_provider={settings.llm_provider!r}. Must be 'openai' or 'anthropic'.\n"
        + _HELP
    )
