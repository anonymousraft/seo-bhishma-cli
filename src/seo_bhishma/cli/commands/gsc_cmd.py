"""``seo-bhishma gsc`` — Google Search Console authorization + lookup.

A one-click login flow that opens the system browser, runs Google's OAuth
consent screen, and stores the resulting token under the user's config dir.
Subsequent ``gsc-probe`` runs (and the AI agent's GSC tools) auto-pick it up.
"""

from __future__ import annotations

import click
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from seo_bhishma.agents.google_auth import (
    GoogleAuthError,
    NoBundledClient,
    clear_token,
    do_oauth_login,
    get_authenticated_email,
    gsc_token_path,
    load_client_config,
    load_saved_credentials,
)
from seo_bhishma.cli._ui import console


@click.group(invoke_without_command=True)
@click.pass_context
def gsc(ctx: click.Context) -> None:
    """Authorize and inspect your Google Search Console connection.

    With no subcommand this prints status (account email + token state).
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(status_cmd)


@gsc.command("login")
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Skip launching a browser (use for SSH / headless shells).",
)
def login_cmd(no_browser: bool) -> None:
    """Authorize SEO Bhishma to access your Google Search Console account."""
    try:
        client_config = load_client_config()
    except NoBundledClient as e:
        console.print(
            Panel(
                str(e),
                title="[yellow]OAuth client not configured[/yellow]",
                title_align="left",
                border_style="yellow",
            )
        )
        raise click.exceptions.Exit(code=2) from None
    except GoogleAuthError as e:
        console.print(f"[red][-] {e}[/red]")
        raise click.exceptions.Exit(code=2) from None

    if not no_browser:
        console.print(
            "[dim]Opening your browser to grant Search Console access… "
            "If nothing appears, try [bold]--no-browser[/bold].[/dim]"
        )
    console.print(f"[dim]Using OAuth client from: {client_config.source}[/dim]")

    try:
        creds = do_oauth_login(no_browser=no_browser)
    except KeyboardInterrupt:
        console.print("[yellow][!] Login cancelled.[/yellow]")
        raise click.exceptions.Exit(code=130) from None
    except Exception as e:
        console.print(
            Panel(
                f"[red]{type(e).__name__}: {e}[/red]\n\n"
                "If a browser opened but didn't redirect back, you can re-run with "
                "[bold]--no-browser[/bold] to paste the code manually.",
                title="[red]Login failed[/red]",
                title_align="left",
                border_style="red",
            )
        )
        raise click.exceptions.Exit(code=1) from None

    email = get_authenticated_email(creds) or "(email not in token)"
    console.print(
        Panel(
            f"[green]✓ Authorized as[/green] [bold]{email}[/bold]\n"
            f"Token saved to [dim]{gsc_token_path()}[/dim]",
            title="[green]Search Console connected[/green]",
            title_align="left",
            border_style="green",
        )
    )


@gsc.command("logout")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def logout_cmd(yes: bool) -> None:
    """Remove the saved GSC OAuth token from this machine."""
    path = gsc_token_path()
    if not path.exists():
        console.print(f"[yellow][!] No saved token at {path}.[/yellow]")
        return
    if not yes and not Confirm.ask(f"Delete {path}?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        return
    clear_token()
    console.print(f"[green][+] Removed {path}.[/green]")


@gsc.command("status")
def status_cmd() -> None:
    """Show whether GSC is connected and which account."""
    path = gsc_token_path()
    creds = load_saved_credentials()
    if creds is None:
        console.print(
            Panel(
                "[red]✗[/red] Not connected.\n"
                "Run [bold]seo-bhishma gsc login[/bold] to authorize.",
                title="Search Console status",
                title_align="left",
                border_style="red",
            )
        )
        return

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    table.add_row("status", "[green]✓ connected[/green]")
    table.add_row("account", get_authenticated_email(creds) or "(email not in token)")
    table.add_row("token", str(path))
    table.add_row("expires", _expiry(creds))
    if creds.scopes:
        table.add_row("scopes", ", ".join(creds.scopes))
    console.print(table)


@gsc.command("sites")
def sites_cmd() -> None:
    """List the Search Console properties the authorized account can access."""
    creds = load_saved_credentials()
    if creds is None:
        console.print(
            "[red][-] Not connected.[/red] Run [bold]seo-bhishma gsc login[/bold] first."
        )
        raise click.exceptions.Exit(code=2)

    from googleapiclient.discovery import build

    from seo_bhishma.core.gsc_probe import list_sites

    try:
        service = build("searchconsole", "v1", credentials=creds)
        sites = list_sites(service)
    except Exception as e:
        console.print(f"[red][-] Failed to list sites: {e}[/red]")
        raise click.exceptions.Exit(code=1) from None

    if not sites:
        console.print(
            "[yellow][!] No Search Console properties found for this account.[/yellow]\n"
            "Verify you own at least one at https://search.google.com/search-console"
        )
        return

    table = Table(title=f"{len(sites)} GSC properties", header_style="bold")
    table.add_column("site")
    table.add_column("permission", style="dim")
    for site in sites:
        table.add_row(site.get("siteUrl", ""), site.get("permissionLevel", ""))
    console.print(table)


def _expiry(creds) -> str:
    expiry = getattr(creds, "expiry", None)
    if expiry is None:
        return "(no expiry recorded)"
    return expiry.isoformat()
