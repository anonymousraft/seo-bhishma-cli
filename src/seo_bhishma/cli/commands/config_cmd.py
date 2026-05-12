"""``seo-bhishma config`` — manage the system-wide user configuration."""

from __future__ import annotations

import click
from rich.prompt import Confirm
from rich.table import Table

from seo_bhishma.agents.validators import (
    validate_anthropic_key,
    validate_openai_key,
)
from seo_bhishma.cli._ui import console
from seo_bhishma.cli.user_config import (
    EDITABLE_FIELDS,
    SECRET_FIELDS,
    UserConfig,
    _mask_secret,
    delete_config,
    load_config,
    save_config,
    user_config_path,
)
from seo_bhishma.cli.wizard import run_wizard


@click.group(invoke_without_command=True)
@click.pass_context
def config(ctx: click.Context) -> None:
    """Inspect or edit the saved user configuration.

    With no subcommand this re-runs the interactive wizard, pre-populated with
    your current values so you can press Enter through anything you want to keep.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(wizard_cmd)


@config.command("wizard")
def wizard_cmd() -> None:
    """Re-run the interactive setup wizard."""
    existing = load_config()
    run_wizard(existing)


@config.command("show")
def show_cmd() -> None:
    """Print the current configuration with secrets masked."""
    cfg = load_config()
    if cfg is None:
        console.print(
            "[yellow][!] No saved configuration. "
            "Run [bold]seo-bhishma config wizard[/bold] to create one.[/yellow]"
        )
        return

    table = Table(title=f"Configuration  ({user_config_path()})", header_style="bold")
    table.add_column("setting", style="cyan", no_wrap=True)
    table.add_column("value")
    for key, value in cfg.model_dump().items():
        if key == "config_version":
            continue
        if key in SECRET_FIELDS:
            display = _mask_secret(str(value)) if value else "[dim](unset)[/dim]"
        elif value == "" or value is None:
            display = "[dim](unset)[/dim]"
        else:
            display = str(value)
        table.add_row(key, display)
    console.print(table)


@config.command("get")
@click.argument("key")
def get_cmd(key: str) -> None:
    """Print one configuration value (unmasked — for scripting).

    Exits non-zero if KEY isn't a known setting.
    """
    if key not in EDITABLE_FIELDS:
        console.print(f"[red][-] Unknown config key: {key}[/red]")
        console.print(f"    Valid keys: {', '.join(EDITABLE_FIELDS)}")
        raise click.exceptions.Exit(code=1)
    cfg = load_config() or UserConfig()
    value = getattr(cfg, key, "")
    click.echo(value)


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_cmd(key: str, value: str) -> None:
    """Set one configuration value and persist it.

    Re-validates against the live API when KEY is ``openai_api_key`` or
    ``anthropic_api_key``. KEY must be a known field; otherwise exits non-zero.
    """
    if key not in EDITABLE_FIELDS:
        console.print(f"[red][-] Unknown config key: {key}[/red]")
        console.print(f"    Valid keys: {', '.join(EDITABLE_FIELDS)}")
        raise click.exceptions.Exit(code=1)

    if key == "openai_api_key" and value:
        console.print("[dim]Validating against the OpenAI API…[/dim]")
        result = validate_openai_key(value)
        if not result.ok:
            console.print(f"[red][-] OpenAI rejected the key: {result.status.value}[/red]")
            if result.detail:
                console.print(f"    [dim]{result.detail}[/dim]")
            raise click.exceptions.Exit(code=1)
    elif key == "anthropic_api_key" and value:
        console.print("[dim]Validating against the Anthropic API…[/dim]")
        result = validate_anthropic_key(value)
        if not result.ok:
            console.print(f"[red][-] Anthropic rejected the key: {result.status.value}[/red]")
            if result.detail:
                console.print(f"    [dim]{result.detail}[/dim]")
            raise click.exceptions.Exit(code=1)
    elif key == "default_interface" and value not in {"chat", "menu"}:
        console.print(f"[red][-] default_interface must be 'chat' or 'menu' (got {value!r}).[/red]")
        raise click.exceptions.Exit(code=1)
    elif key == "llm_provider" and value not in {"", "openai", "anthropic"}:
        console.print(
            f"[red][-] llm_provider must be 'openai', 'anthropic', or '' (got {value!r}).[/red]"
        )
        raise click.exceptions.Exit(code=1)
    elif key == "log_level" and value not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        console.print(
            f"[red][-] log_level must be DEBUG/INFO/WARNING/ERROR (got {value!r}).[/red]"
        )
        raise click.exceptions.Exit(code=1)

    cfg = load_config() or UserConfig()
    updated = cfg.model_copy(update={key: value})
    save_config(updated)

    display = _mask_secret(value) if key in SECRET_FIELDS and value else value
    console.print(f"[green][+] {key} = {display}[/green]")


@config.command("path")
def path_cmd() -> None:
    """Print the absolute path of the configuration file."""
    click.echo(str(user_config_path()))


@config.command("reset")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
def reset_cmd(yes: bool) -> None:
    """Delete the saved configuration. The next launch will re-run the wizard."""
    path = user_config_path()
    if not path.exists():
        console.print(f"[yellow][!] No config to remove at {path}.[/yellow]")
        return
    if not yes:
        if not Confirm.ask(f"Delete [bold]{path}[/bold]?", default=False):
            console.print("[yellow]Aborted.[/yellow]")
            return
    delete_config()
    console.print(f"[green][+] Removed {path}.[/green]")
