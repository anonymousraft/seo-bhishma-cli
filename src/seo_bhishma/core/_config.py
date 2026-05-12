"""Cached Settings accessor for core modules.

Core functions should accept explicit params (api_key, model, etc.) but may
fall back to ``get_settings()`` when called from contexts (MCP/agents) that
load configuration from environment variables.
"""

from __future__ import annotations

from functools import lru_cache

from seo_bhishma.config.settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached Settings (testing helper)."""
    get_settings.cache_clear()
