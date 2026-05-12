"""Interactive first-run configuration wizard.

Five sections; each is independently skippable. The wizard is driven by Rich
prompts so it inherits SEO Bhishma's existing terminal styling, and uses live
API-key validation for OpenAI/Anthropic (see ``agents/validators.py``) so the
user knows immediately whether their key is good.

Public entry point: :func:`run_wizard`. It returns the resulting
:class:`UserConfig` *and* persists it to disk. Callers that need to know
where the file landed should call :func:`seo_bhishma.cli.user_config.user_config_path`.
"""

from __future__ import annotations

from collections.abc import Iterable

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from seo_bhishma.agents.validators import (
    ValidationResult,
    ValidationStatus,
    validate_anthropic_key,
    validate_openai_key,
)
from seo_bhishma.cli._ui import console
from seo_bhishma.cli.user_config import (
    SECRET_FIELDS,
    UserConfig,
    _mask_secret,
    consume_legacy_default_interface,
    save_config,
    user_config_path,
)
from seo_bhishma.config.constants import CLI_NAME, CLI_VERSION
from seo_bhishma.config.settings import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
)

_TOTAL_SECTIONS = 5


def run_wizard(existing: UserConfig | None = None) -> UserConfig:
    """Run the full wizard and persist the result. Returns the saved config.

    ``existing`` pre-populates defaults when the user re-runs ``config wizard``
    on a system that already has saved settings — they can press Enter to keep
    each current value.
    """
    _print_intro()
    if existing is None:
        # Upgrade case: a pre-wizard preferences.yaml is on disk. Use its
        # default_interface as the starting point so the user's old choice
        # survives the upgrade, then delete the legacy file.
        legacy_interface = consume_legacy_default_interface()
        if legacy_interface is not None:
            existing = UserConfig(default_interface=legacy_interface)
    state = existing.model_copy(deep=True) if existing else UserConfig()

    state = _section_interface(state, step=1)
    state = _section_llm_provider(state, step=2)
    state = _section_gsc(state, step=3)
    state = _section_captcha(state, step=4)
    state = _section_advanced(state, step=5)

    _print_summary(state)
    if not Confirm.ask("[bold]Save and continue?[/bold]", default=True):
        console.print("[yellow][!] Configuration not saved. No changes written.[/yellow]")
        return state

    path = save_config(state)
    console.print(f"[green][+] Saved to {path}[/green]")
    return state


# ---------------------------------------------------------------------------
# Header / summary helpers
# ---------------------------------------------------------------------------


def _print_intro() -> None:
    body = Text.from_markup(
        f"Let's set up [bold]{CLI_NAME}[/bold] v{CLI_VERSION}. This takes about a minute.\n\n"
        "You can [cyan]skip any section[/cyan] — defaults work for most users. "
        "Sensitive values are saved to a file readable only by you "
        f"([dim]{user_config_path()}[/dim]).\n\n"
        "Re-run anytime with [bold]seo-bhishma config wizard[/bold]."
    )
    console.print(Panel(body, title="First-run setup", border_style="green"))


def _section_header(step: int, title: str, description: str) -> None:
    body = Text.from_markup(f"{description}")
    console.print(
        Panel(
            body,
            title=f"[{step}/{_TOTAL_SECTIONS}] {title}",
            border_style="cyan",
        )
    )


def _print_summary(state: UserConfig) -> None:
    table = Table(
        title="Your configuration", show_header=True, header_style="bold", title_style="bold green"
    )
    table.add_column("setting", style="cyan", no_wrap=True)
    table.add_column("value")
    for key, value in state.model_dump().items():
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


# ---------------------------------------------------------------------------
# Section 1 — interface preference
# ---------------------------------------------------------------------------


def _section_interface(state: UserConfig, *, step: int) -> UserConfig:
    _section_header(
        step,
        "Default interface",
        "When you run [bold]seo-bhishma[/bold] with no arguments, which interface should launch?\n"
        "  • [bold]chat[/bold] — AI agent REPL (recommended).\n"
        "  • [bold]menu[/bold] — Numbered legacy menu of nine tools.",
    )
    choice = Prompt.ask(
        "Default interface", choices=["chat", "menu"], default=state.default_interface
    )
    return state.model_copy(update={"default_interface": choice})


# ---------------------------------------------------------------------------
# Section 2 — LLM provider
# ---------------------------------------------------------------------------


def _section_llm_provider(state: UserConfig, *, step: int) -> UserConfig:
    _section_header(
        step,
        "LLM provider for AI chat",
        "AI chat needs at least one provider. Keys are validated against the API "
        "before they are saved.\n"
        "  • [bold]openai[/bold] — uses GPT models (gpt-4o-mini default).\n"
        "  • [bold]anthropic[/bold] — uses Claude models (claude-sonnet-4-5 default).\n"
        "  • [bold]both[/bold] — configure both keys; pick one as default.\n"
        "  • [bold]skip[/bold] — leave for later (chat will refuse to start).",
    )
    choice = Prompt.ask(
        "Which provider(s) to set up?",
        choices=["openai", "anthropic", "both", "skip"],
        default=_default_provider_choice(state),
    )
    if choice == "skip":
        console.print("[yellow][!] Skipping LLM setup. AI chat won't run until a key is set.[/yellow]")
        return state

    update: dict[str, str] = {}
    set_openai = choice in {"openai", "both"}
    set_anthropic = choice in {"anthropic", "both"}

    if set_openai:
        key = _prompt_and_validate_key(
            provider="OpenAI",
            current=state.openai_api_key,
            validator=validate_openai_key,
        )
        if key is not None:
            update["openai_api_key"] = key

    if set_anthropic:
        key = _prompt_and_validate_key(
            provider="Anthropic",
            current=state.anthropic_api_key,
            validator=validate_anthropic_key,
        )
        if key is not None:
            update["anthropic_api_key"] = key

    # Default provider: ask only when both are now configured.
    final = state.model_copy(update=update) if update else state
    if final.openai_api_key and final.anthropic_api_key:
        default_provider = Prompt.ask(
            "Default provider when both are configured",
            choices=["openai", "anthropic"],
            default=state.llm_provider or "openai",
        )
        update["llm_provider"] = default_provider
    elif final.openai_api_key:
        update["llm_provider"] = "openai"
    elif final.anthropic_api_key:
        update["llm_provider"] = "anthropic"

    # Optional model override.
    provider_for_default = update.get("llm_provider", state.llm_provider) or "openai"
    suggested = (
        DEFAULT_ANTHROPIC_MODEL if provider_for_default == "anthropic" else DEFAULT_OPENAI_MODEL
    )
    model = Prompt.ask(
        f"Override model name? Press Enter for [bold]{suggested}[/bold]",
        default=state.llm_model or "",
        show_default=False,
    )
    if model.strip():
        update["llm_model"] = model.strip()

    return state.model_copy(update=update)


def _default_provider_choice(state: UserConfig) -> str:
    if state.openai_api_key and state.anthropic_api_key:
        return "both"
    if state.openai_api_key:
        return "openai"
    if state.anthropic_api_key:
        return "anthropic"
    return "openai"


def _prompt_and_validate_key(
    *,
    provider: str,
    current: str,
    validator,
    max_attempts: int = 3,
) -> str | None:
    """Prompt for an API key, validate it live, allow retries. Returns the key or None."""
    if current:
        change = Confirm.ask(
            f"{provider} key already set ([dim]{_mask_secret(current)}[/dim]). Replace it?",
            default=False,
        )
        if not change:
            return current

    for attempt in range(1, max_attempts + 1):
        key = Prompt.ask(f"{provider} API key", password=True)
        if not key.strip():
            console.print(
                f"[yellow][!] No key entered — leaving {provider} unconfigured.[/yellow]"
            )
            return None
        console.print(f"[dim]Validating against the {provider} API…[/dim]")
        result = validator(key)
        if result.ok:
            console.print(f"[green][+] {provider} key works.[/green]")
            return key
        _explain_validation_failure(provider, result)
        if result.status == ValidationStatus.NETWORK:
            if Confirm.ask("Save the key anyway and validate later?", default=False):
                return key
        if attempt >= max_attempts:
            console.print(
                f"[yellow][!] Skipping {provider} after {max_attempts} attempts.[/yellow]"
            )
            return None
        if not result.retriable or not Confirm.ask("Try a different key?", default=True):
            return None
    return None


def _explain_validation_failure(provider: str, result: ValidationResult) -> None:
    headline = {
        ValidationStatus.UNAUTHORIZED: f"{provider} rejected the key (401 / invalid).",
        ValidationStatus.FORBIDDEN: f"{provider} returned 403 (key revoked or region blocked).",
        ValidationStatus.RATE_LIMITED: f"{provider} rate-limited the validation request (429).",
        ValidationStatus.NETWORK: f"Couldn't reach {provider} — network error.",
        ValidationStatus.UNKNOWN: f"{provider} returned an unexpected response.",
    }[result.status]
    console.print(f"[red][-] {headline}[/red]")
    if result.detail:
        console.print(f"    [dim]{result.detail}[/dim]")


# ---------------------------------------------------------------------------
# Section 3 — Google Search Console
# ---------------------------------------------------------------------------


def _section_gsc(state: UserConfig, *, step: int) -> UserConfig:
    """Section 3: Google Search Console — opens the browser for a one-click login."""
    from seo_bhishma.agents.google_auth import (
        GoogleAuthError,
        NoBundledClient,
        do_oauth_login,
        get_authenticated_email,
        load_saved_credentials,
    )

    _section_header(
        step,
        "Google Search Console (optional)",
        "Connect GSC to use [bold]gsc-probe[/bold] and let the AI agent answer "
        "Search Console queries.\n"
        "[dim]Opens your browser to grant access — about 10 seconds.[/dim]",
    )

    # Already connected? Offer to skip.
    existing = load_saved_credentials()
    if existing is not None:
        email = get_authenticated_email(existing) or "(account)"
        console.print(f"[green]✓ Already connected as {email}.[/green]")
        if not Confirm.ask("Re-authorize anyway?", default=False):
            return state

    if not Confirm.ask("Connect Search Console now?", default=False):
        console.print(
            "[dim]Skipped. You can do this later with [bold]seo-bhishma gsc login[/bold].[/dim]"
        )
        return state

    try:
        creds = do_oauth_login()
    except NoBundledClient as e:
        console.print(
            "[yellow][!] OAuth client not configured in this build:[/yellow] " + str(e)
        )
        console.print(
            "[dim]Skipping GSC. Run [bold]seo-bhishma gsc login[/bold] after setting "
            "[bold]gsc_credentials_path[/bold] in your config.[/dim]"
        )
        return state
    except KeyboardInterrupt:
        console.print("[yellow][!] Login cancelled — skipping GSC.[/yellow]")
        return state
    except (GoogleAuthError, Exception) as e:  # noqa: BLE001
        console.print(f"[red][-] Login failed: {type(e).__name__}: {e}[/red]")
        console.print(
            "[dim]Skipping GSC. Try [bold]seo-bhishma gsc login --no-browser[/bold] "
            "from a shell with internet access.[/dim]"
        )
        return state

    email = get_authenticated_email(creds) or "(account)"
    console.print(f"[green]✓ Connected as {email}.[/green]")
    return state


# ---------------------------------------------------------------------------
# Section 4 — CAPTCHA service
# ---------------------------------------------------------------------------


def _section_captcha(state: UserConfig, *, step: int) -> UserConfig:
    _section_header(
        step,
        "CAPTCHA solving service (optional, advanced)",
        "[bold]index-spy[/bold] can fall back to 2captcha or anti-captcha when Google blocks "
        "your IP. Skip unless you check large URL batches without proxies.",
    )
    if not Confirm.ask("Configure a CAPTCHA service?", default=bool(state.captcha_service)):
        return state
    service = Prompt.ask(
        "Service",
        choices=["2captcha", "anti-captcha", "skip"],
        default=state.captcha_service or "2captcha",
    )
    if service == "skip":
        return state
    api_key = Prompt.ask(f"{service} API key", default=state.captcha_api_key, password=True)
    if not api_key.strip():
        console.print("[yellow][!] No key entered — skipping CAPTCHA.[/yellow]")
        return state
    return state.model_copy(
        update={"captcha_service": service, "captcha_api_key": api_key.strip()}
    )


# ---------------------------------------------------------------------------
# Section 5 — Advanced
# ---------------------------------------------------------------------------


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def _section_advanced(state: UserConfig, *, step: int) -> UserConfig:
    _section_header(
        step,
        "Advanced (optional)",
        "spaCy model and log level. Defaults are fine for most users.",
    )
    if not Confirm.ask("Configure advanced settings?", default=False):
        return state
    spacy_model = Prompt.ask("spaCy model", default=state.spacy_model)
    log_level = Prompt.ask("Log level", choices=list(_LOG_LEVELS), default=state.log_level)
    return state.model_copy(
        update={"spacy_model": spacy_model, "log_level": log_level}
    )


__all__: Iterable[str] = ("run_wizard",)
