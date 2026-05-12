"""Redirection Genius CLI: NLP-based source→destination URL mapping."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core.redirection_genius import map_urls


def _start_redirection() -> None:
    input_file = Prompt.ask("[cyan]Enter the path to the input CSV file[/cyan]")
    if not Path(input_file).is_file():
        console.print(f"[bold red][-] Input file not found: {input_file}[/bold red]")
        return

    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        console.print(f"[bold red][-] Failed to read input file: {e}[/bold red]")
        return

    if "source" not in df.columns or "destination" not in df.columns:
        console.print(
            "[bold red][-] Input file must contain 'source' and 'destination' columns.[/bold red]"
        )
        return
    if df.empty:
        console.print("[bold red][-] Input file is empty.[/bold red]")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = f"url_mapping_output_{timestamp}.csv"
    output_file = Prompt.ask(
        "[cyan]Enter the path to the output CSV file[/cyan]", default=default_out
    )
    use_web = Prompt.ask(
        "[cyan]Use web content check for low-confidence matches?[/cyan]",
        choices=["yes", "no"],
        default="no",
    ) == "yes"
    rate_limit = 0.0
    if use_web:
        try:
            rate_limit = float(
                Prompt.ask("[cyan]Rate limit in seconds between requests[/cyan]", default="1")
            )
        except ValueError:
            rate_limit = 1.0

    source_urls = df["source"].dropna().astype(str).tolist()
    dest_urls = df["destination"].dropna().astype(str).tolist()
    console.print("[green][+] Starting URL mapping...[/green]")

    with make_progress() as progress:
        task = progress.add_task("[+] Mapping URLs...", total=len(source_urls))

        def on_progress(completed: int, total: int) -> None:
            progress.update(task, completed=completed, total=total)

        results = map_urls(
            source_urls,
            dest_urls,
            use_web_content=use_web,
            rate_limit=rate_limit,
            on_progress=on_progress,
        )

    out_df = pd.DataFrame([r.model_dump() for r in results])
    out_df.to_csv(output_file, index=False, encoding="utf-8")
    console.print(f"[green][+] URL mapping completed. Output saved to {output_file}[/green]")
    console.print("[blue][+] Summary:[/blue]")
    console.print(f"[blue][+] Total Source URLs: {len(source_urls)}[/blue]")
    console.print(f"[blue][+] Total Destination URLs: {len(dest_urls)}[/blue]")
    console.print(f"[blue][+] Mapped URLs: {len(results)}[/blue]")


@click.command()
def redirection_genius() -> None:
    """Powerful & intelligent redirect URL mapper."""
    while True:
        console.print(
            tool_panel(
                "RedirectGenius", "Powerful & intelligent URL to URL redirection mapper."
            )
        )
        console.print("[yellow]1. Start URL redirection mapping[/yellow]")
        console.print("[red]0. Exit[/red]")
        choice = Prompt.ask(
            "[yellow bold]Please choose an option[/yellow bold]", choices=["1", "0"]
        )

        if choice == "1":
            _start_redirection()
        else:
            console.print("[bold red]Thank you for using RedirectGenius![/bold red]")
            return
