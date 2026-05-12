"""Shared Rich UI helpers for CLI commands."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from seo_bhishma.config.constants import CLI_AUTHOR, CLI_NAME, CLI_VERSION

console = Console()


def tool_panel(title: str, body: str) -> Panel:
    """Build a consistent header Panel for a tool."""
    return Panel(
        body,
        title=title,
        border_style="green",
        subtitle=f"{CLI_NAME}, v{CLI_VERSION} by {CLI_AUTHOR}",
        subtitle_align="right",
    )


def make_progress(transient: bool = True) -> Progress:
    """Build a Rich Progress with the bar/spinner column set used across tools."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        transient=transient,
        console=console,
    )
