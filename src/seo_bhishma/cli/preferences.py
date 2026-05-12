"""Backward-compatibility shim over :mod:`seo_bhishma.cli.user_config`.

The pre-wizard ``preferences.yaml`` file has been folded into the richer
``config.yaml`` written by the first-run wizard. This module keeps the old
``Preferences`` dataclass + ``load_preferences()`` / ``save_preferences()``
public API working so existing tests don't break — internally everything
delegates to :mod:`user_config`, which also handles the one-time migration
from the legacy file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from seo_bhishma.cli.user_config import (
    UserConfig,
    legacy_preferences_path,
    load_config,
    save_config,
    user_config_path,
)

Interface = Literal["chat", "menu"]


@dataclass
class Preferences:
    """Legacy preferences shape — kept as a thin view onto :class:`UserConfig`."""

    default_interface: Interface = "chat"


def preferences_path() -> Path:
    """Return the legacy preferences path (used by tests that sandbox via env var).

    Prefer :func:`user_config_path` in new code.
    """
    return legacy_preferences_path()


def load_preferences() -> Preferences | None:
    """Return saved preferences, migrating from legacy ``preferences.yaml`` if needed."""
    config = load_config()
    if config is None:
        return None
    return Preferences(default_interface=config.default_interface)


def save_preferences(prefs: Preferences) -> Path:
    """Persist ``prefs.default_interface`` into the unified ``config.yaml``."""
    existing = load_config() or UserConfig()
    updated = existing.model_copy(update={"default_interface": prefs.default_interface})
    save_config(updated)
    return user_config_path()
