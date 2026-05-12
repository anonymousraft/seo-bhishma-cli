"""System-wide user configuration for the SEO Bhishma CLI.

This module owns the on-disk configuration file that the first-run wizard
populates: API keys, default LLM provider, GSC OAuth path, CAPTCHA service,
NLP defaults, logging, and UI preference. The same file is loaded as the
lowest-priority source of :class:`seo_bhishma.config.settings.Settings` via
``settings_customise_sources``, so env vars and ``.env`` always win.

Resolution order for the file path (mirrors the previous ``preferences.yaml``
behavior so existing test sandboxes keep working):

* ``$SEO_BHISHMA_HOME/config.yaml`` when ``SEO_BHISHMA_HOME`` is set, else
* ``%APPDATA%/seo-bhishma/config.yaml`` on Windows, or
* ``$XDG_CONFIG_HOME/seo-bhishma/config.yaml`` (defaults to ``~/.config/...``)
  on POSIX.

The file is written with ``chmod 0o600`` on POSIX. On Windows we rely on the
default per-user `%APPDATA%` ACL.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

Interface = Literal["chat", "menu"]

_CONFIG_FILENAME = "config.yaml"
_LEGACY_PREFS_FILENAME = "preferences.yaml"

# Bump when introducing a backward-incompatible change in the on-disk schema.
SCHEMA_VERSION = 1

# Fields whose values are secrets — masked in ``UserConfig.masked_dict()`` and in
# the ``config show`` / wizard-summary outputs.
SECRET_FIELDS: frozenset[str] = frozenset(
    {"openai_api_key", "anthropic_api_key", "captcha_api_key"}
)

# Fields the user is allowed to edit via ``config set``. Anything outside this
# set rejects.
EDITABLE_FIELDS: tuple[str, ...] = (
    "default_interface",
    "llm_provider",
    "llm_model",
    "openai_api_key",
    "anthropic_api_key",
    "gsc_credentials_path",
    "gsc_token_path",
    "captcha_service",
    "captcha_api_key",
    "spacy_model",
    "log_level",
)


class UserConfig(BaseModel):
    """On-disk shape of the user's saved configuration.

    Field names match :class:`seo_bhishma.config.settings.Settings` 1:1 so the
    YAML can be layered directly into pydantic-settings.
    """

    config_version: int = Field(default=SCHEMA_VERSION)

    # UI preference (was its own preferences.yaml file before).
    default_interface: Interface = "chat"

    # LLM provider
    llm_provider: str = ""
    llm_model: str = ""

    # API keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Google Search Console
    gsc_credentials_path: str = ""
    gsc_token_path: str = "token.pickle"

    # CAPTCHA service (IndexSpy)
    captcha_service: str = ""
    captcha_api_key: str = ""

    # NLP
    spacy_model: str = "en_core_web_sm"

    # Logging
    log_level: str = "INFO"

    def masked_dict(self) -> dict[str, Any]:
        """Return a plain ``dict`` with secrets replaced by a masked preview."""
        out: dict[str, Any] = {}
        for key, value in self.model_dump().items():
            if key in SECRET_FIELDS and value:
                out[key] = _mask_secret(value)
            else:
                out[key] = value
        return out

    def settings_overlay(self) -> dict[str, str]:
        """Return only the fields that should overlay into ``Settings``.

        Excludes ``config_version`` and ``default_interface`` (UI-only) so the
        layered settings source stays focused on env-var-equivalent values.
        """
        skip = {"config_version", "default_interface"}
        return {k: v for k, v in self.model_dump().items() if k not in skip}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    override = os.environ.get("SEO_BHISHMA_HOME")
    if override:
        return Path(override)
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "seo-bhishma"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "seo-bhishma"


def user_config_path() -> Path:
    """Return the absolute path of the user config file."""
    return _config_dir() / _CONFIG_FILENAME


def legacy_preferences_path() -> Path:
    """Return the path of the pre-wizard ``preferences.yaml`` (kept for migration)."""
    return _config_dir() / _LEGACY_PREFS_FILENAME


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_config() -> UserConfig | None:
    """Load the saved config.

    Returns ``None`` when no config exists *and* no legacy preferences file is
    available — that signals "first run, launch the wizard".

    If only the legacy ``preferences.yaml`` exists, it is migrated in place to
    the new ``config.yaml`` and the legacy file is deleted.
    """
    path = user_config_path()
    if path.exists():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return None
        return UserConfig.model_validate(_coerce_legacy_fields(raw))

    legacy = legacy_preferences_path()
    if legacy.exists():
        migrated = _migrate_legacy_preferences(legacy)
        if migrated is not None:
            return migrated

    return None


def save_config(config: UserConfig) -> Path:
    """Persist the config to disk, set restrictive perms on POSIX, return the path.

    Creates parent directories as needed. Writes atomically (temp + rename) so
    a crash mid-write can't leave the file half-written.
    """
    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump()
    yaml_text = (
        "# seo-bhishma user configuration.\n"
        "# Edit via `seo-bhishma config set <key> <value>` or re-run "
        "`seo-bhishma config wizard`.\n"
        "# On POSIX this file is mode 0600 (owner read/write only).\n"
        + yaml.safe_dump(data, sort_keys=False)
    )

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml_text, encoding="utf-8")

    # Tighten permissions before moving so the final file is never world-readable.
    if not sys.platform.startswith("win"):
        try:
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Some filesystems (e.g. FAT mounts) don't support chmod; that's fine.
            pass

    os.replace(tmp, path)
    return path


def delete_config() -> bool:
    """Remove the saved config (used by ``config reset``). Returns True if removed."""
    path = user_config_path()
    if not path.exists():
        return False
    path.unlink()
    return True


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------


def _migrate_legacy_preferences(legacy_path: Path) -> UserConfig | None:
    """Read the pre-wizard ``preferences.yaml``, write a new ``config.yaml``, delete the old one."""
    try:
        raw = yaml.safe_load(legacy_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    interface = raw.get("default_interface", "chat")
    if interface not in ("chat", "menu"):
        interface = "chat"
    config = UserConfig(default_interface=interface)
    save_config(config)
    try:
        legacy_path.unlink()
    except OSError:
        pass
    return config


def _coerce_legacy_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Drop keys that aren't part of the current schema rather than raising."""
    known = set(UserConfig.model_fields.keys())
    return {k: v for k, v in raw.items() if k in known}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_secret(value: str) -> str:
    """Render a secret as ``sk-...…7c2a`` (first 4, last 4)."""
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}…{value[-4:]}"
