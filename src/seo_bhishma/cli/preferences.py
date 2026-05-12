"""User preferences for the SEO Bhishma CLI.

Stores the user's choice between the AI chat default and the legacy numbered
menu. Preferences live in:

* ``$SEO_BHISHMA_HOME/preferences.yaml`` when ``SEO_BHISHMA_HOME`` is set, else
* ``~/.config/seo-bhishma/preferences.yaml`` on POSIX, or
* ``%APPDATA%\\seo-bhishma\\preferences.yaml`` on Windows.

The format is intentionally tiny and forward-compatible (a plain YAML dict).
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import yaml

Interface = Literal["chat", "menu"]


@dataclass
class Preferences:
    """User-level CLI preferences."""

    default_interface: Interface = "chat"


def preferences_path() -> Path:
    """Resolve the preferences file path."""
    override = os.environ.get("SEO_BHISHMA_HOME")
    if override:
        return Path(override) / "preferences.yaml"
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "seo-bhishma" / "preferences.yaml"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "seo-bhishma" / "preferences.yaml"


def load_preferences() -> Preferences | None:
    """Return saved preferences, or ``None`` if the user hasn't been onboarded yet."""
    path = preferences_path()
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    iface = data.get("default_interface", "chat")
    if iface not in ("chat", "menu"):
        iface = "chat"
    return Preferences(default_interface=iface)


def save_preferences(prefs: Preferences) -> Path:
    """Write preferences to disk, creating parent directories as needed."""
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(asdict(prefs)), encoding="utf-8")
    return path
