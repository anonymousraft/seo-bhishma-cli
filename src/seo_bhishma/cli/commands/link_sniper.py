"""Link Sniper CLI: bulk backlink liveness + anchor-text verification."""

from __future__ import annotations

from datetime import datetime

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core.link_sniper import (
    batch_check_backlinks,
    check_backlink,
    read_backlinks_from_csv,
)
from seo_bhishma.models.link_sniper import BacklinkCheckResult


def _print_single_result(result: BacklinkCheckResult) -> None:
    """Render a single backlink check result with status coloring."""
    console.print(f"[cyan][+] Backlink URL: {result.backlink_url}[/cyan]")
    console.print(f"[cyan][+] Target URL: {result.target_url}[/cyan]")

    status_color = {
        "Live": "green",
        "Not Live": "red",
        "Not Found": "red",
        "Error": "yellow",
    }.get(result.status, "yellow")
    console.print(f"[{status_color}][+] Status: {result.status}[/{status_color}]")

    anchor_color = {"Present": "green", "Missing": "red"}.get(result.anchor_status, "yellow")
    console.print(
        f"[{anchor_color}][+] Anchor Text Status: {result.anchor_status}[/{anchor_color}]"
    )
    if result.actual_anchor_text:
        console.print(f"[green][+] Actual Anchor Text: {result.actual_anchor_text}[/green]")
    console.print(f"[cyan][+] Link Exists: {result.link_exists}[/cyan]")
    if result.rel_values:
        rel_str = ", ".join(result.rel_values)
        follow = "dofollow" if result.is_dofollow else "nofollow"
        console.print(f"[cyan][+] rel: {rel_str} ({follow})[/cyan]")


@click.command()
def link_sniper() -> None:
    """Check if backlinks are live and verify anchor texts."""
    while True:
        console.print(
            tool_panel(
                "Link Sniper",
                "Check bulk backlinks to determine if they are live or not.",
            )
        )
        console.print("[cyan]1. Check a single URL[/cyan]")
        console.print("[cyan]2. Check URLs from a file[/cyan]")
        console.print("[red bold]3. Exit[/red bold]")
        choice = Prompt.ask("[cyan bold]Enter your choice[/cyan bold]", choices=["1", "2", "3"])

        if choice == "1":
            backlink_url = Prompt.ask("[cyan]Enter the backlink URL[/cyan]")
            target_url = Prompt.ask("[cyan]Enter the target URL[/cyan]")
            expected_anchor = Prompt.ask(
                "[cyan]Enter the expected anchor text (optional)[/cyan]", default=""
            )
            result = check_backlink(backlink_url, target_url, expected_anchor)
            _print_single_result(result)

        elif choice == "2":
            input_file = Prompt.ask(
                "[cyan]Enter the path to the input file (CSV/JSON)[/cyan]"
            )
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            default_out = f"backlink_report_{timestamp}.csv"
            output_file = Prompt.ask(
                "[cyan]Enter the path to the output CSV file[/cyan]", default=default_out
            )

            try:
                checks = read_backlinks_from_csv(input_file)
            except Exception as e:
                console.print(f"[red][-] Failed to read input: {e}[/red]")
                continue

            console.print("[green bold][+] Processing URLs...[/green bold]")

            with make_progress() as progress:
                task = progress.add_task("[+] Checking URLs...", total=len(checks))

                def on_progress(completed: int, total: int) -> None:
                    progress.update(task, completed=completed)

                results = batch_check_backlinks(checks, max_workers=10, on_progress=on_progress)

            df = pd.DataFrame([r.model_dump() for r in results])
            df.to_csv(output_file, index=False, encoding="utf-8")
            found = sum(1 for r in results if r.link_exists == "Yes")
            console.print(f"[green][+] Report generated: {output_file}[/green]")
            console.print(
                f"[green bold][+] Summary: {found} target URLs found out of "
                f"{len(results)} processed.[/green bold]"
            )

        elif choice == "3":
            console.print("[red bold]Exiting LinkSniper. Goodbye![/red bold]")
            return

        console.print("=" * 50)
