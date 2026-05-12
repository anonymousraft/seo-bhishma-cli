"""Site Mapper CLI: download a sitemap (incl. nested/gzipped) and export to CSV."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core._utils import extract_domain
from seo_bhishma.core.site_mapper import download_and_parse_sitemap


@click.command()
@click.option("--sitemap-url", default=None, help="URL of the sitemap to download and parse")
@click.option("--output-file", default=None, help="Path to the output CSV file")
def site_mapper(sitemap_url: str | None, output_file: str | None) -> None:
    """Download and parse sitemaps, export URLs to CSV."""
    console.print(
        tool_panel(
            "Sitemapper",
            "Download sitemap into a CSV file. Supports nested & compressed sitemaps.",
        )
    )

    if not sitemap_url:
        sitemap_url = Prompt.ask("[cyan]Enter the URL of the sitemap (supports .xml and .gz)[/cyan]")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    domain = extract_domain(sitemap_url) or "sitemap"

    if output_file:
        p = Path(output_file)
        output_file = str(p.parent / f"{p.stem}_{timestamp}{p.suffix}")
    else:
        default = f"{domain}_sitemap_{timestamp}.csv"
        output_file = Prompt.ask("[cyan]Enter the output CSV file[/cyan]", default=default)

    console.print("[green][+] Downloading and parsing sitemap...[/green]")

    with make_progress() as progress:
        task = progress.add_task("[+] Parsing URLs...", total=None)

        def on_progress(completed: int, total: int) -> None:
            progress.update(task, total=total, completed=completed)

        result = download_and_parse_sitemap(sitemap_url, on_progress=on_progress)

    if result is None:
        console.print("[bold red][-] Failed to process sitemap.[/bold red]")
        return

    rows = [u.model_dump() for u in result.urls]
    df = pd.DataFrame(rows)
    df.to_csv(output_file, index=False, encoding="utf-8")
    console.print(
        f"[green][+] {len(rows)} URLs from {result.total_sitemaps_parsed} "
        f"sitemap(s) saved to {output_file}[/green]"
    )
