"""GSC Probe CLI: Google Search Console data extraction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.config.settings import Settings
from seo_bhishma.core.gsc_probe import (
    authenticate_gsc,
    fetch_search_analytics,
    fetch_sitemaps,
    fetch_url_inspection,
    get_available_dates,
    list_sites,
)
from seo_bhishma.models.gsc_probe import SearchAnalyticsFilter

_AVAILABLE_DIMENSIONS = "date,query,page,country,device,searchAppearance"


def _save_dir() -> Path:
    out_dir = Path("gsc_data")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _select_site(service) -> str | None:
    """Prompt the user to pick a site from the GSC account."""
    sites = list_sites(service)
    if not sites:
        console.print("[bold red][-] No sites returned from GSC. Check credentials.[/bold red]")
        return None

    console.print("[green][+] Available sites in your GSC account:[/green]")
    for index, site in enumerate(sites, start=1):
        console.print(f"[cyan]{index}.[/cyan] {site['siteUrl']}")

    raw = Prompt.ask(
        "[magenta]Enter the number of the site (or 'exit' to quit)[/magenta]"
    )
    if raw.lower() == "exit":
        return None

    try:
        idx = int(raw) - 1
    except ValueError:
        console.print("[red][-] Invalid selection.[/red]")
        return None
    if not (0 <= idx < len(sites)):
        console.print("[red][-] Site number out of range.[/red]")
        return None
    return sites[idx]["siteUrl"]


def _do_search_analytics(service, site_url: str, start_date: str, end_date: str) -> None:
    start_input = Prompt.ask(
        "[magenta]Start date (YYYY-MM-DD)[/magenta]", default=start_date
    )
    end_input = Prompt.ask("[magenta]End date (YYYY-MM-DD)[/magenta]", default=end_date)
    dimensions_raw = Prompt.ask(
        f"[magenta]Dimensions (comma-separated, available: {_AVAILABLE_DIMENSIONS})[/magenta]",
        default="date",
    )
    dimensions = [d.strip() for d in dimensions_raw.split(",") if d.strip()]
    search_type = Prompt.ask(
        "[magenta]Search type[/magenta]",
        choices=["web", "image", "video", "news"],
        default="web",
    )

    row_limit_raw = Prompt.ask(
        "[magenta]Row limit ('max' for no cap)[/magenta]", default="25000"
    )
    if row_limit_raw.lower() == "max":
        row_limit: int | None = None
    else:
        try:
            row_limit = int(row_limit_raw)
        except ValueError:
            console.print("[red][-] Invalid row limit, defaulting to 25000.[/red]")
            row_limit = 25000

    filters: list[SearchAnalyticsFilter] = []
    if Prompt.ask("[magenta]Add filters?[/magenta]", choices=["yes", "no"], default="no") == "yes":
        for dim in dimensions:
            if (
                Prompt.ask(
                    f"[magenta]Filter for '{dim}'?[/magenta]",
                    choices=["yes", "no"],
                    default="no",
                )
                == "yes"
            ):
                op = Prompt.ask(
                    "[magenta]Filter operator[/magenta]",
                    choices=[
                        "equals",
                        "contains",
                        "notContains",
                        "includingRegex",
                        "excludingRegex",
                    ],
                    default="equals",
                )
                expr = Prompt.ask("[magenta]Filter expression[/magenta]")
                filters.append(
                    SearchAnalyticsFilter(dimension=dim, operator=op, expression=expr)
                )

    device = Prompt.ask("[magenta]Device filter (blank to skip)[/magenta]", default="")
    if device:
        filters.append(
            SearchAnalyticsFilter(dimension="device", operator="equals", expression=device)
        )
    country = Prompt.ask("[magenta]Country filter (ISO code, blank to skip)[/magenta]", default="")
    if country:
        filters.append(
            SearchAnalyticsFilter(dimension="country", operator="equals", expression=country)
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = str(_save_dir() / f"gsc_output_{timestamp}.csv")
    output_file = Prompt.ask("[magenta]Output CSV file[/magenta]", default=default_out)

    console.print("[green][+] Fetching GSC data...[/green]")
    with make_progress() as progress:
        task = progress.add_task("[+] Fetching GSC...", total=row_limit)

        def on_progress(completed: int, total: int) -> None:
            progress.update(task, total=total or row_limit or 1, completed=completed)

        result = fetch_search_analytics(
            service,
            site_url,
            start_input,
            end_input,
            dimensions=dimensions,
            row_limit=row_limit,
            search_type=search_type,
            filters=filters or None,
            on_progress=on_progress,
        )

    if not result.rows:
        console.print("[red][-] No data returned. Adjust query parameters and retry.[/red]")
        return

    flat: list[dict] = []
    for r in result.rows:
        row: dict = {}
        for dim, key in zip(dimensions, r.keys):
            row[dim] = key
        row.update(
            clicks=r.clicks, impressions=r.impressions, ctr=r.ctr, position=r.position
        )
        flat.append(row)
    pd.DataFrame(flat).to_csv(output_file, index=False, encoding="utf-8")
    console.print(f"[green][+] {len(result.rows)} rows saved to {output_file}[/green]")


def _do_sitemaps(service, site_url: str) -> None:
    console.print("[green][+] Fetching sitemaps data...[/green]")
    sitemaps = fetch_sitemaps(service, site_url)
    if not sitemaps:
        console.print("[red][-] No sitemaps found.[/red]")
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    domain = site_url.replace("https://", "").replace("http://", "").rstrip("/").replace("/", "_")
    output_file = str(_save_dir() / f"{domain}_sitemaps_{timestamp}.csv")
    pd.DataFrame([s.model_dump() for s in sitemaps]).to_csv(
        output_file, index=False, encoding="utf-8"
    )
    console.print(f"[green][+] {len(sitemaps)} sitemap(s) saved to {output_file}[/green]")


def _do_url_inspection(service, site_url: str) -> None:
    sub_choice = Prompt.ask(
        "[magenta]Inspect [1] single URL or [2] batch from CSV?[/magenta]", choices=["1", "2"]
    )
    if sub_choice == "1":
        url = Prompt.ask("[magenta]URL to inspect[/magenta]")
        results = fetch_url_inspection(service, site_url, [url])
        if results:
            console.print(results[0].model_dump())
    else:
        csv_file = Prompt.ask("[magenta]Path to CSV containing 'urls' column[/magenta]")
        try:
            df = pd.read_csv(csv_file, encoding="utf-8")
        except Exception as e:
            console.print(f"[red][-] Failed to read CSV: {e}[/red]")
            return
        if "urls" not in df.columns:
            console.print("[red][-] CSV must contain a 'urls' column.[/red]")
            return
        urls = df["urls"].dropna().astype(str).tolist()

        with make_progress() as progress:
            task = progress.add_task("[+] Inspecting URLs...", total=len(urls))

            def on_progress(completed: int, total: int) -> None:
                progress.update(task, completed=completed, total=total)

            results = fetch_url_inspection(service, site_url, urls, on_progress=on_progress)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_out = str(_save_dir() / f"url_inspection_{timestamp}.csv")
        output_file = Prompt.ask("[magenta]Output CSV[/magenta]", default=default_out)
        pd.DataFrame([r.model_dump() for r in results]).to_csv(
            output_file, index=False, encoding="utf-8"
        )
        console.print(f"[green][+] Saved {len(results)} inspection results to {output_file}[/green]")


@click.command()
def gsc_probe() -> None:
    """Google Search Console Data Extraction Tool."""
    settings = Settings()
    creds_path = settings.gsc_credentials_path or None

    while True:
        console.print(
            tool_panel(
                "GSC Probe",
                "Extract Search Console data: analytics, sitemaps, URL inspection.",
            )
        )

        if not creds_path:
            creds_path = Prompt.ask("[yellow]Path to OAuth credentials JSON[/yellow]")
        try:
            service = authenticate_gsc(creds_path, settings.gsc_token_path or "token.pickle")
        except Exception as e:
            console.print(f"[bold red][-] Authentication failed: {e}[/bold red]")
            creds_path = None
            continue

        site_url = _select_site(service)
        if site_url is None:
            console.print("[bold red]Thank you for using GSC Probe! Goodbye![/bold red]")
            return

        start_date, _ = get_available_dates(service, site_url)
        end_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        if not start_date:
            console.print("[bold red][-] Unable to fetch available dates.[/bold red]")
            continue

        while True:
            console.print("\n[yellow]Select the type of data to extract:[/yellow]\n")
            sub_choice = Prompt.ask(
                "[magenta]1. Search Analytics  2. Sitemaps  3. URL Inspection  4. Back[/magenta]",
                choices=["1", "2", "3", "4"],
            )
            if sub_choice == "1":
                _do_search_analytics(service, site_url, start_date, end_date)
            elif sub_choice == "2":
                _do_sitemaps(service, site_url)
            elif sub_choice == "3":
                _do_url_inspection(service, site_url)
            else:
                break
