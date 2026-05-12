"""Domain Insight CLI: IP / DNS / WHOIS / robots.txt / tech-stack lookups."""

from __future__ import annotations

import asyncio
import datetime as _dt

import click
import pandas as pd
from rich.prompt import Prompt

from seo_bhishma.cli._ui import console, make_progress, tool_panel
from seo_bhishma.core._utils import extract_domain
from seo_bhishma.core.domain_insight import (
    check_urls_against_robots,
    fetch_robots_txt,
    fetch_robots_txt_playwright,
    find_subdomains,
    get_dns_records,
    get_ip_address,
    get_ip_details,
    get_security_headers,
    get_ssl_certificate,
    get_whois_info,
    is_valid_domain_or_url,
    reverse_ip_lookup_playwright,
    tech_analysis,
)
from seo_bhishma.core.site_mapper import download_and_parse_sitemap


def _prompt_domain(current: str | None) -> str | None:
    """Prompt for a valid domain (looping until the input parses)."""
    if current:
        return current
    while True:
        raw = Prompt.ask("[cyan bold]Enter the domain name or URL[/cyan bold]")
        if is_valid_domain_or_url(raw):
            return extract_domain(raw)
        console.print("[bold red][-] Invalid domain or URL. Please try again.[/bold red]")


def _save_text(filename: str, lines: list[str]) -> str:
    """Write lines to a text file and return the path."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filename


def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _do_reverse_ip(domain: str) -> None:
    ip = get_ip_address(domain)
    if not ip:
        console.print(f"[bold red][-] Could not resolve IP for {domain}.[/bold red]")
        return
    console.print(f"[cyan][+] IP: {ip}[/cyan]")
    console.print("[blue][*] Launching Playwright browser for reverse-IP lookup.[/blue]")
    result = asyncio.run(reverse_ip_lookup_playwright(ip))
    if not result:
        console.print("[bold red][-] Reverse IP lookup failed.[/bold red]")
        return
    console.print(f"[bold green][+] {result.title}[/bold green]")
    for key, value in result.table_info.items():
        console.print(f"{key}: {value}")
    console.print(f"[bold][+] {len(result.domains)} domains on this IP[/bold]")
    out = f"{domain}_reverse_ip_{_timestamp()}.txt"
    lines = [f"Title: {result.title}", "", "Table:"]
    lines += [f"{k}: {v}" for k, v in result.table_info.items()]
    lines += ["", "Domains:"] + list(result.domains)
    _save_text(out, lines)
    console.print(f"[green][+] Saved to {out}[/green]")


def _do_subdomains(domain: str) -> None:
    console.print("[blue][*] Enumerating subdomains via sublist3r...[/blue]")
    subs = find_subdomains(domain)
    if not subs:
        console.print("[yellow][!] No subdomains found.[/yellow]")
        return
    out = f"{domain}_subdomains_{_timestamp()}.txt"
    _save_text(out, list(subs))
    console.print(f"[green][+] {len(subs)} subdomains saved to {out}[/green]")


def _do_dns(domain: str) -> None:
    dns = get_dns_records(domain)
    out = f"{domain}_dns_records_{_timestamp()}.txt"
    lines: list[str] = []
    for field in ("a", "aaaa", "mx", "ns", "txt", "cname"):
        values = getattr(dns, field)
        lines.append(f"{field.upper()}: {', '.join(values) if values else 'No record found'}")
    _save_text(out, lines)
    for line in lines:
        console.print(line)
    console.print(f"[green][+] DNS records saved to {out}[/green]")


def _do_robots_check(domain: str) -> None:
    console.print("[blue][*] Fetching robots.txt...[/blue]")
    robots = fetch_robots_txt(domain) or asyncio.run(fetch_robots_txt_playwright(domain))
    if robots is None:
        console.print("[bold red][-] robots.txt not found.[/bold red]")
        return
    console.print(f"[bold green][+] {len(robots.disallow_rules)} disallow rules found.[/bold green]")
    if not robots.disallow_rules:
        console.print("[green][+] No disallow directives. Nothing to check.[/green]")
        return

    sitemaps = robots.sitemaps or [
        Prompt.ask(
            f"[yellow]No Sitemap directive found. Sitemap URL for {domain}?[/yellow]"
        )
    ]

    all_urls: list[tuple[str, str]] = []
    for sm in sitemaps:
        result = download_and_parse_sitemap(sm)
        if result is None:
            continue
        all_urls.extend((sm, url.loc) for url in result.urls)

    if not all_urls:
        console.print("[yellow][!] No URLs extracted from sitemaps.[/yellow]")
        return

    results = check_urls_against_robots(robots.disallow_rules, all_urls)
    blocked = [r for r in results if r.status == "Blocked"]
    if not blocked:
        console.print("[bold green][+] No URLs are blocked by robots.txt.[/bold green]")
        return
    out = f"{domain}_robots_check_{_timestamp()}.csv"
    pd.DataFrame([r.model_dump() for r in results]).to_csv(out, index=False, encoding="utf-8")
    console.print(f"[bold red][-] {len(blocked)} URL(s) blocked. Results saved to {out}[/bold red]")


def _do_whois(domain: str) -> None:
    info = get_whois_info(domain)
    if not info.data:
        console.print("[bold red][-] WHOIS lookup failed.[/bold red]")
        return
    for key, value in info.data.items():
        console.print(f"{key}: {value}")
    out = f"{domain}_whois_{_timestamp()}.txt"
    _save_text(out, [f"{k}: {v}" for k, v in info.data.items()])
    console.print(f"[green][+] WHOIS saved to {out}[/green]")


def _do_ip_details(domain: str) -> None:
    ip = get_ip_address(domain)
    if not ip:
        console.print(f"[bold red][-] Could not resolve {domain}.[/bold red]")
        return
    details = get_ip_details(ip)
    for k, v in details.model_dump().items():
        console.print(f"{k}: {v}")
    out = f"{domain}_ip_details_{_timestamp()}.txt"
    _save_text(out, [f"{k}: {v}" for k, v in details.model_dump().items()])
    console.print(f"[green][+] IP details saved to {out}[/green]")


def _do_tech_stack(domain: str) -> None:
    with make_progress() as progress:
        progress.add_task("[+] Detecting tech stack...", total=None)
        result = tech_analysis(domain)
    if not result.technologies:
        console.print("[bold red][-] Tech stack analysis failed.[/bold red]")
        return
    for tech in result.technologies:
        console.print(f"[yellow]{tech}[/yellow]")
    out = f"{domain}_tech_lookup_{_timestamp()}.txt"
    _save_text(out, list(result.technologies))
    console.print(f"[bold green][+] Tech stack saved to {out}[/bold green]")


def _do_ssl(domain: str) -> None:
    info = get_ssl_certificate(domain)
    if info.error:
        console.print(f"[bold red][-] SSL lookup failed: {info.error}[/bold red]")
        return
    console.print(f"[cyan]Issuer:[/cyan] {info.issuer}")
    console.print(f"[cyan]Subject:[/cyan] {info.subject}")
    console.print(f"[cyan]Valid:[/cyan] {info.valid_from} → {info.valid_to}")
    console.print(f"[cyan]SANs ({len(info.subject_alt_names)}):[/cyan] {', '.join(info.subject_alt_names)}")


def _do_security_headers(domain: str) -> None:
    info = get_security_headers(domain)
    if info.error:
        console.print(f"[bold red][-] Failed: {info.error}[/bold red]")
        return
    console.print(f"[bold]Grade:[/bold] {info.grade}  (URL: {info.url})")
    for h, v in info.headers.items():
        console.print(f"  [green]{h}[/green]: {v}")
    if info.missing:
        console.print(f"[yellow]Missing: {', '.join(info.missing)}[/yellow]")


@click.command()
@click.option("--domain", default=None, help="Domain to analyze")
def domain_insight(domain: str | None) -> None:
    """Advanced domain information gathering tool."""
    console.print(
        tool_panel("Domain Insight", "Powerful domain information gathering tool.")
    )

    current = domain
    while True:
        current = _prompt_domain(current)
        if current is None:
            return
        console.print(f"[cyan]\nCurrent domain: {current}[/cyan]")

        console.print("[yellow]1. Check other websites hosted on the same IP[/yellow]")
        console.print("[yellow]2. Identify subdomains[/yellow]")
        console.print("[yellow]3. Check DNS records[/yellow]")
        console.print("[yellow]4. Check robots.txt[/yellow]")
        console.print("[yellow]5. Check WHOIS record[/yellow]")
        console.print("[yellow]6. Get IP address details[/yellow]")
        console.print("[yellow]7. Tech stack analysis[/yellow]")
        console.print("[yellow]8. SSL/TLS certificate[/yellow]")
        console.print("[yellow]9. HTTP security headers[/yellow]")
        console.print("[red]0. Exit[/red]")

        choice = Prompt.ask(
            "[yellow bold]Please choose an option[/yellow bold]",
            choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        )

        handler = {
            "1": _do_reverse_ip,
            "2": _do_subdomains,
            "3": _do_dns,
            "4": _do_robots_check,
            "5": _do_whois,
            "6": _do_ip_details,
            "7": _do_tech_stack,
            "8": _do_ssl,
            "9": _do_security_headers,
        }.get(choice)

        if choice == "0":
            console.print("[bold red]Thank you for using Domain Insight![/bold red]")
            return
        if handler:
            try:
                handler(current)
            except Exception as e:
                console.print(f"[bold red][-] {choice}: {e}[/bold red]")
