"""Index Spy CLI: bulk Google indexing checks with proxy + captcha handling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core.index_spy import batch_check_indexing, check_indexing_status
from seo_bhishma.models.index_spy import (
    CaptchaConfig,
    CaptchaHandling,
    CheckMethod,
    ProxyConfig,
)


def _read_proxy_file(path: str) -> list[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def _prompt_proxy_config() -> ProxyConfig | None:
    if Prompt.ask("[cyan]Use proxies?[/cyan]", choices=["yes", "no"], default="no") != "yes":
        return None
    proxy_file = Prompt.ask("[cyan]Path to proxy file[/cyan]")
    try:
        proxies = _read_proxy_file(proxy_file)
    except Exception as e:
        console.print(f"[red][-] Failed to read proxy file: {e}[/red]")
        return None
    if not proxies:
        console.print("[red][-] Proxy file is empty.[/red]")
        return None
    mode_choice = Prompt.ask(
        "[cyan]Proxy mode[/cyan]",
        choices=["HTTP", "HTTPS", "Both", "SOCKS4", "SOCKS5"],
        default="Both",
    ).lower()
    mode_map = {
        "http": ["http"],
        "https": ["https"],
        "both": ["http", "https"],
        "socks4": ["socks4"],
        "socks5": ["socks5"],
    }
    return ProxyConfig(proxy_list=proxies, mode=mode_map[mode_choice])


def _prompt_captcha_config() -> CaptchaConfig | None:
    if (
        Prompt.ask(
            "[cyan]Use a paid CAPTCHA solving service?[/cyan]",
            choices=["yes", "no"],
            default="no",
        )
        != "yes"
    ):
        return None
    service = Prompt.ask(
        "[cyan]Service[/cyan]", choices=["2captcha", "anti-captcha"], default="2captcha"
    )
    api_key = Prompt.ask("[cyan]API key[/cyan]")
    return CaptchaConfig(service=service, api_key=api_key)


def _prompt_method_and_handling() -> tuple[CheckMethod, CaptchaHandling, bool]:
    method_choice = Prompt.ask(
        "[cyan]Checking method[/cyan]",
        choices=["HTMLSession", "Playwright"],
        default="HTMLSession",
    )
    method = (
        CheckMethod.HTML_SESSION if method_choice == "HTMLSession" else CheckMethod.PLAYWRIGHT
    )
    headless = False
    handling = CaptchaHandling.AUTOMATIC
    if method == CheckMethod.PLAYWRIGHT:
        headless = (
            Prompt.ask(
                "[cyan]Run Playwright headless?[/cyan]", choices=["yes", "no"], default="no"
            )
            == "yes"
        )
        if not headless:
            choice = Prompt.ask(
                "[cyan]How to handle captchas?[/cyan]",
                choices=["By user", "Automatic"],
                default="By user",
            )
            handling = (
                CaptchaHandling.BY_USER if choice == "By user" else CaptchaHandling.AUTOMATIC
            )
    return method, handling, headless


@click.command()
def index_spy() -> None:
    """Check Google indexing status for bulk URLs."""
    proxy_config = _prompt_proxy_config()
    captcha_config = _prompt_captcha_config()
    try:
        rate_limit = float(
            Prompt.ask(
                "[cyan]Delay between requests in seconds (0 for none)[/cyan]", default="0"
            )
        )
    except ValueError:
        rate_limit = 0.0

    while True:
        console.print(
            tool_panel("IndexSpy", "Bulk Indexing Checker with Proxy & Browser support.")
        )
        console.print("[cyan]1. Check a single URL[/cyan]")
        console.print("[cyan]2. Check URLs from a file[/cyan]")
        console.print("[red bold]3. Exit[/red bold]")
        choice = Prompt.ask(
            "[cyan bold]Enter your choice[/cyan bold]", choices=["1", "2", "3"]
        )

        if choice == "3":
            console.print("[red bold]Exiting IndexSpy. Goodbye![/red bold]")
            return

        if choice == "1":
            url = Prompt.ask("[cyan]URL to check[/cyan]")
            method, handling, headless = _prompt_method_and_handling()
            proxy_dict = None
            if proxy_config and proxy_config.proxy_list:
                from seo_bhishma.core.index_spy import ProxyRotator

                rotator = ProxyRotator(proxy_config.proxy_list, proxy_config.mode)
                proxy_dict = rotator.find_valid(method)
                if proxy_dict:
                    console.print(f"[blue][+] Using proxy: {proxy_dict}[/blue]")
                else:
                    console.print("[yellow][!] No valid proxy; proceeding without one.[/yellow]")

            with make_progress() as progress:
                progress.add_task("[+] Checking indexing status...", total=None)
                result = check_indexing_status(
                    url,
                    method=method,
                    proxy=proxy_dict,
                    captcha_config=captcha_config,
                    captcha_handling=handling,
                    headless=headless,
                    rate_limit=rate_limit,
                )
            color = "green" if result.status == "Indexed" else "red"
            console.print(f"[cyan][+] URL: {result.url}[/cyan]")
            console.print(f"[{color}][+] Indexing Status: {result.status}[/{color}]")
            console.print(f"[cyan][+] Proxy used: {result.proxy_used}[/cyan]")

        elif choice == "2":
            input_file = Prompt.ask("[cyan]Path to input CSV/JSON[/cyan]")
            try:
                if input_file.endswith(".json"):
                    df = pd.read_json(input_file)
                else:
                    df = pd.read_csv(input_file)
            except Exception as e:
                console.print(f"[red][-] Failed to read input: {e}[/red]")
                continue
            if "url" not in df.columns:
                console.print("[red][-] Input file must contain a 'url' column.[/red]")
                continue
            urls = df["url"].dropna().astype(str).tolist()

            method, handling, headless = _prompt_method_and_handling()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_out = f"index_spy_output_{timestamp}.csv"
            output_file = Prompt.ask(
                "[cyan]Output CSV file[/cyan]", default=default_out
            )

            with make_progress() as progress:
                task = progress.add_task("[+] Processing URLs...", total=len(urls))

                def on_progress(completed: int, total: int) -> None:
                    progress.update(task, completed=completed, total=total)

                batch = batch_check_indexing(
                    urls,
                    method=method,
                    proxy_config=proxy_config,
                    captcha_config=captcha_config,
                    captcha_handling=handling,
                    headless=headless,
                    rate_limit=rate_limit,
                    on_progress=on_progress,
                )

            pd.DataFrame([r.model_dump() for r in batch.results]).to_csv(
                output_file, index=False, encoding="utf-8"
            )
            console.print(
                f"[green bold][+] Saved {batch.total_checked} results to {output_file}[/green bold]"
            )
            console.print(
                f"[green]Indexed: {batch.total_indexed} | "
                f"Not Indexed: {batch.total_not_indexed} | "
                f"Errors: {batch.total_errors}[/green]"
            )

        console.print("\n" + "=" * 50 + "\n")
