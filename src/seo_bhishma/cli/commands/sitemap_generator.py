"""Sitemap Generator CLI: build single or nested XML sitemaps from a URL list."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core.sitemap_generator import (
    generate_nested_sitemaps,
    generate_sitemap,
    write_sitemap,
)


def _read_urls(file_path: str) -> list[str]:
    """Read URLs from a CSV file (expects a 'url' column)."""
    df = pd.read_csv(file_path)
    col = "url" if "url" in df.columns else df.columns[0]
    return df[col].dropna().astype(str).tolist()


@click.command()
@click.option("--input-file", default=None, help="Path to the input CSV file containing URLs")
@click.option("--output-dir", default="sitemaps/", help="Output directory for sitemaps")
@click.option("--nested", is_flag=True, default=False, help="Generate nested sitemaps")
@click.option("--url-limit", default=50000, help="Max URLs per sitemap (nested mode)")
@click.option("--compressed", is_flag=True, default=False, help="Gzip the output files")
@click.option("--priority", default="", help="Priority for URLs (e.g. 0.8)")
@click.option("--frequency", default="", help="Change frequency (daily/weekly/monthly/yearly)")
@click.option("--lastmod", default="", help="Last modified date (YYYY-MM-DDTHH:MM:SS+00:00)")
def sitemap_generator(
    input_file: str | None,
    output_dir: str,
    nested: bool,
    url_limit: int,
    compressed: bool,
    priority: str,
    frequency: str,
    lastmod: str,
) -> None:
    """Generate XML sitemaps from a list of URLs."""
    while True:
        console.print(
            tool_panel(
                "Sitemap Generator",
                "Generate sitemap from a list of URLs. Supports nested & compressed output.",
            )
        )
        console.print("[cyan]1. Generate a single sitemap[/cyan]")
        console.print("[cyan]2. Generate nested sitemaps[/cyan]")
        console.print("[bold red]3. Exit[/bold red]")
        choice = Prompt.ask("[cyan bold]Enter your choice[/cyan bold]", choices=["1", "2", "3"])

        if choice == "3":
            console.print("[bold red]Exiting Sitemap Generator. Goodbye![/bold red]")
            return

        if not input_file:
            input_file = Prompt.ask("[cyan]Enter the input CSV file[/cyan]", default="input.csv")
        if not output_dir:
            output_dir = Prompt.ask("[cyan]Enter the output directory[/cyan]", default="sitemaps/")
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        use_nested = nested or choice == "2"
        effective_limit = url_limit
        if use_nested and url_limit == 50000:
            effective_limit = int(
                Prompt.ask(
                    "[cyan]Enter the maximum number of URLs per sitemap[/cyan]",
                    default="50000",
                )
            )
        if not compressed:
            compressed_choice = Prompt.ask(
                "[cyan]Compress output files?[/cyan]", choices=["yes", "no"], default="no"
            )
            compressed = compressed_choice == "yes"
        if not priority:
            priority = Prompt.ask("[cyan]Priority (blank to skip)[/cyan]", default="")
        if not frequency:
            frequency = Prompt.ask("[cyan]Change frequency (blank to skip)[/cyan]", default="")
        if not lastmod:
            lastmod = Prompt.ask(
                "[cyan]Last modified (blank for now)[/cyan]", default=""
            ) or datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")

        try:
            urls = _read_urls(input_file)
        except Exception as e:
            console.print(f"[red][-] Failed to read input file: {e}[/red]")
            input_file = None
            continue
        if not urls:
            console.print("[bold red][-] No URLs found in input file.[/bold red]")
            input_file = None
            continue

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            if not use_nested:
                console.print("[green bold][+] Generating single sitemap...[/green bold]")
                content = generate_sitemap(
                    urls,
                    priority=priority or None,
                    frequency=frequency or None,
                    lastmod=lastmod,
                )
                filename = f"sitemap_{timestamp}.xml" + (".gz" if compressed else "")
                file_path = str(output_path / filename)
                write_sitemap(file_path, content, compressed=compressed)
                console.print(f"[green bold][+] Saved sitemap to {file_path}[/green bold]")
            else:
                console.print("[green bold][+] Generating nested sitemaps...[/green bold]")
                with make_progress() as progress:
                    task = progress.add_task("[+] Creating sitemaps...", total=None)

                    def on_progress(completed: int, total: int) -> None:
                        progress.update(task, total=total, completed=completed)

                    files, index_path = generate_nested_sitemaps(
                        urls,
                        output_dir=str(output_path),
                        url_limit=effective_limit,
                        priority=priority or None,
                        frequency=frequency or None,
                        lastmod=lastmod,
                        compressed=compressed,
                        on_progress=on_progress,
                    )
                console.print(f"[green bold][+] Sitemap index saved to {index_path}[/green bold]")
                console.print(
                    f"[green bold][+] Total sitemaps created: {len(files)}[/green bold]"
                )
        except Exception as e:
            console.print(f"[bold red][-] Failed to generate sitemaps: {e}[/bold red]")

        # Reset per-iteration state so the next loop re-prompts.
        input_file = None
        compressed = False
        priority = ""
        frequency = ""
        lastmod = ""

        console.print("\n" + "=" * 50 + "\n")
