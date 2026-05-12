"""Logging setup for seo_bhishma.

Call ``setup_logging()`` from CLI/MCP/agent entry points. Library modules
themselves never configure handlers - they only ``logging.getLogger(__name__)``.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def setup_logging(level: str | int | None = None, rich: bool = True) -> None:
    """Configure the root logger.

    Args:
        level: Log level (e.g. ``"INFO"``). When ``None``, reads from
            ``Settings.log_level``.
        rich: If True, use ``rich.logging.RichHandler``. Falls back to a
            plain ``StreamHandler`` when Rich is unavailable.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    if level is None:
        from seo_bhishma.config.settings import Settings

        level = Settings().log_level

    if isinstance(level, str):
        level = level.upper()

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any pre-existing handlers added by libraries
    for h in list(root.handlers):
        root.removeHandler(h)

    if rich:
        try:
            from rich.logging import RichHandler

            handler: logging.Handler = RichHandler(
                rich_tracebacks=True, show_path=False, markup=True
            )
        except ImportError:
            handler = logging.StreamHandler()
    else:
        handler = logging.StreamHandler()

    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    root.addHandler(handler)
    _CONFIGURED = True


def reset_logging() -> None:
    """Reset the configured flag (testing helper)."""
    global _CONFIGURED
    _CONFIGURED = False
