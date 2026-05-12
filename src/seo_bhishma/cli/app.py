"""Entry point for the ``seo-bhishma`` CLI.

Bare ``seo-bhishma`` runs the first-run wizard when no config file exists,
then dispatches to either the AI chat or the legacy numbered menu based on
the user's saved ``default_interface``.
"""

from __future__ import annotations

import sys

import click
from art import text2art
from rich import box
from rich.prompt import Prompt
from rich.table import Table

from seo_bhishma.cli._ui import console, tool_panel
from seo_bhishma.cli.commands import (
    chat,
    config,
    domain_insight,
    gsc_probe,
    hannibal,
    index_spy,
    keyword_sorcerer,
    link_sniper,
    redirection_genius,
    site_mapper,
    sitemap_generator,
)
from seo_bhishma.cli.user_config import (
    UserConfig,
    load_config,
    save_config,
)
from seo_bhishma.cli.wizard import run_wizard
from seo_bhishma.config.constants import (
    CLI_AUTHOR,
    CLI_MESSAGE,
    CLI_NAME,
    CLI_VERSION,
)
from seo_bhishma.config.settings import Settings

_MENU_ITEMS = [
    ("1", "GSC Probe", gsc_probe),
    ("2", "Domain Insights", domain_insight),
    ("3", "Keyword Sorcerer", keyword_sorcerer),
    ("4", "Hannibal", hannibal),
    ("5", "IndexSpy", index_spy),
    ("6", "Redirection Genius", redirection_genius),
    ("7", "LinkSniper", link_sniper),
    ("8", "SiteMapper", site_mapper),
    ("9", "Sitemap Generator", sitemap_generator),
]


@click.group(invoke_without_command=True)
@click.version_option(version=f"v{CLI_VERSION}", prog_name=CLI_NAME)
@click.option("--word", is_flag=True, default=False, help="save the trees!")
@click.pass_context
def cli(ctx: click.Context, word: bool) -> None:
    """SEO Bhishma — a toolkit of SEO utilities."""
    if word:
        console.print(tool_panel("Message to World", CLI_MESSAGE))
        sys.exit(0)

    if ctx.invoked_subcommand is not None:
        return

    ctx.invoke(intro)

    user_config = load_config()
    if user_config is None:
        user_config = run_wizard()

    # Defensive: if the saved config wants chat but no LLM is resolvable
    # (no env var, no key in YAML), finish setup before launching chat
    # instead of erroring out at the chat entry point.
    if user_config.default_interface == "chat" and not Settings().resolve_provider():
        console.print(
            "[yellow]Chat requires an LLM provider, but none is configured yet. "
            "Running setup…[/yellow]\n"
        )
        user_config = run_wizard(existing=user_config)

    if user_config.default_interface == "chat":
        ctx.invoke(chat)
    else:
        ctx.invoke(menu)


@cli.command()
def intro() -> None:
    """Print the SEO Bhishma intro banner."""
    ascii_art = text2art(CLI_NAME, font="tarty2")
    console.print(f"[bold green]{ascii_art}[/bold green]")
    console.print(f"[italic green]v{CLI_VERSION}, {CLI_AUTHOR}\n[/italic green]")
    console.print("[dim white]Giving back to the community.[/dim white]")
    console.print("[dim white]Support: [underline]https://t.ly/hitendra[/underline][/dim white]\n")


@cli.command()
@click.pass_context
def menu(ctx: click.Context) -> None:
    """Main interactive numbered menu (legacy v2-style)."""
    while True:
        table = Table(show_header=False, box=box.ROUNDED, style="dim white")
        for key, label, _cmd in _MENU_ITEMS:
            table.add_row(f"[bold white]{key}.[/bold white]", f"[white]{label}[/white]")
        table.add_row("[bold red]0.[/bold red]", "[red]Exit[/red]")
        console.print(table)

        choices = [k for k, _, _ in _MENU_ITEMS] + ["0"]
        choice = Prompt.ask("[bold white]Enter your choice[/bold white]", choices=choices)

        if choice == "0":
            console.print(f"[bold red]Exiting {CLI_NAME}. Goodbye![/bold red]")
            return

        for key, _label, command in _MENU_ITEMS:
            if choice == key:
                try:
                    ctx.invoke(command)
                except click.Abort:
                    console.print("[yellow][!] Operation cancelled.[/yellow]")
                except Exception as e:
                    console.print(f"[bold red][-] An error occurred: {e}[/bold red]")
                break


@cli.command("set-default")
@click.argument("interface", type=click.Choice(["chat", "menu"]))
def set_default(interface: str) -> None:
    """Set the default interface launched by bare ``seo-bhishma``.

    Thin wrapper over ``seo-bhishma config set default_interface <interface>``.
    """
    existing = load_config() or UserConfig()
    updated = existing.model_copy(update={"default_interface": interface})
    path = save_config(updated)
    console.print(
        f"[green][+] Default interface set to [bold]{interface}[/bold]. Saved to {path}.[/green]"
    )


# Register all subcommands as top-level commands too (so `seo-bhishma link-sniper` works)
for _key, _label, _command in _MENU_ITEMS:
    cli.add_command(_command)

# `chat` is the AI-native entry point — registered top-level but not in the numbered menu.
cli.add_command(chat)
# `config` is the wizard / inspector / editor for the saved user configuration.
cli.add_command(config)


if __name__ == "__main__":
    cli()
