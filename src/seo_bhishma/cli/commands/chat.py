"""``seo-bhishma chat`` — AI-native conversational interface to all SEO tools.

Wraps :func:`seo_bhishma.agents.graph.build_agent` in a Rich REPL with:

* Token streaming for assistant messages.
* Dimmed ``[tool] name(args)`` traces before each tool runs.
* Tiered tool authorization via :class:`ToolAuthSession`.
* Slash commands: ``/help``, ``/clear``, ``/menu``, ``/tools``, ``/model``,
  ``/save``, ``/quit``.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import click
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from seo_bhishma.agents.graph import (
    ToolAuthSession,
    build_agent,
    classify_tool_calls,
    needs_user_confirmation,
)
from seo_bhishma.agents.llm import LlmConfigError
from seo_bhishma.agents.tools import ALL_TOOLS
from seo_bhishma.cli._ui import console, tool_panel
from seo_bhishma.config.constants import CLI_NAME, CLI_VERSION
from seo_bhishma.config.settings import Settings

_TIER_STYLE = {
    "auto": "dim cyan",
    "confirm_once": "yellow",
    "confirm_each": "bold magenta",
}

_HELP_TEXT = """\
**Slash commands**

- `/help` — this message
- `/tools` — list every tool the agent can call, grouped by authorization tier
- `/clear` — start a fresh conversation (discards history)
- `/menu` — drop into the legacy numbered menu
- `/model <name>` — switch model mid-session (e.g. `/model gpt-4o`)
- `/save <path>` — write the current transcript to a markdown file
- `/quit` or `/exit` — leave chat

Type anything else to talk to the agent. Tools that touch costs, time, or \
files will ask permission before running.
"""


# ---------------------------------------------------------------------------
# Pretty rendering helpers
# ---------------------------------------------------------------------------


def _render_tool_args(args: dict) -> str:
    """Format tool arguments compactly for the trace line."""
    if not args:
        return ""
    parts: list[str] = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 60:
            v = v[:57] + "..."
        elif isinstance(v, list) and len(v) > 5:
            v = f"[{len(v)} items]"
        parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def _silence_noisy_loggers() -> None:
    """Stop core/tool error logs from leaking onto the chat surface.

    Anything that should reach the user comes through tool result panels or
    explicit ``console.print`` calls. Internal ``logger.error(...)`` lines
    are still useful in debug mode but they have no business being printed
    next to assistant tokens during a chat turn.
    """
    for name in (
        "seo_bhishma",
        "sublist3r",
        "httpx",
        "httpcore",
        "openai",
        "anthropic",
        "urllib3",
    ):
        logger = logging.getLogger(name)
        logger.setLevel(logging.CRITICAL + 1)
        logger.propagate = False


def _render_tool_result(tool_name: str, content: str) -> None:
    """Render a single tool result in a compact Rich Panel.

    Detects ``{"error": "..."}`` shape (produced by the silencer in
    ``agents/tools.py``) and renders with a red ✗ instead of green ✓.
    """
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        data = content

    is_error = isinstance(data, dict) and "error" in data and len(data) == 1
    if is_error:
        body = Text.from_markup(f"[red]✗ {data['error']}[/red]")
        border = "red"
        title_icon = "[red]✗[/red]"
    else:
        body = _format_result_body(data)
        border = "green"
        title_icon = "[green]✓[/green]"

    console.print(
        Panel(
            body,
            title=f"{title_icon} {tool_name}",
            title_align="left",
            border_style=border,
            padding=(0, 1),
        )
    )


def _format_result_body(data):
    """Render the inside of a successful tool-result panel."""
    if isinstance(data, dict):
        # Tabular preview if the tool returned a `head: [{...}]` shape.
        if "head" in data and isinstance(data["head"], list) and data["head"]:
            preview = _format_table(data["head"], title="preview (first rows)")
            extras = {k: v for k, v in data.items() if k != "head"}
            return _stack(preview, _format_kv(extras) if extras else None)
        if "sample_urls" in data and isinstance(data["sample_urls"], list):
            text = Text("\n".join(data["sample_urls"][:20]))
            extras = {k: v for k, v in data.items() if k != "sample_urls"}
            return _stack(text, _format_kv(extras) if extras else None)
        return _format_kv(data)

    if isinstance(data, list) and data and isinstance(data[0], dict):
        return _format_table(data, title="tool result")

    pretty = json.dumps(data, indent=2, default=str)
    return Syntax(pretty, "json", theme="ansi_dark", line_numbers=False, padding=0)


def _stack(*items):
    """Stack multiple Rich renderables with a blank line between them."""
    from rich.console import Group

    parts = []
    for item in items:
        if item is None:
            continue
        if parts:
            parts.append(Text(""))
        parts.append(item)
    return Group(*parts) if parts else Text("")


def _format_kv(data: dict) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, default=str)
            if len(v) > 160:
                v = v[:157] + "…"
        elif v is None or v == "":
            v = "[dim](empty)[/dim]"
        table.add_row(str(k), str(v))
    return table


def _format_table(rows: list[dict], title: str = "") -> Table:
    columns = list(rows[0].keys())
    table = Table(title=title or None, header_style="bold", title_style="dim")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(row.get(c, "")) for c in columns])
    return table


# ---------------------------------------------------------------------------
# REPL state
# ---------------------------------------------------------------------------


class ChatSession:
    """One run of the chat REPL — owns the agent, thread id, and auth session."""

    def __init__(self, model: str | None = None) -> None:
        self.settings = Settings()
        self.model = model
        self.agent = build_agent(self.settings, model=self.model)
        self.thread_id = str(uuid.uuid4())
        self.auth = ToolAuthSession()
        self.transcript: list[dict] = []  # for /save

    # -- lifecycle ----------------------------------------------------------

    def reset(self) -> None:
        self.thread_id = str(uuid.uuid4())
        self.auth = ToolAuthSession()
        self.transcript = []

    def swap_model(self, model: str) -> None:
        self.model = model
        self.agent = build_agent(self.settings, model=self.model)
        self.reset()

    @property
    def config(self) -> dict:
        return {"configurable": {"thread_id": self.thread_id}}

    # -- one user turn ------------------------------------------------------

    def turn(self, user_message: str) -> None:
        """Run one user→agent turn, handling authorization interrupts mid-flight."""
        self.transcript.append({"role": "user", "content": user_message})
        input_payload: dict | None = {"messages": [HumanMessage(content=user_message)]}

        while True:
            self._stream_until_interrupt(input_payload)
            input_payload = None  # subsequent loops resume from checkpoint

            state = self.agent.get_state(self.config)
            if "tools" not in (state.next or ()):
                self._record_last_ai_message(state)
                return

            messages = state.values.get("messages", [])
            pending = classify_tool_calls(messages)
            blocking = needs_user_confirmation(pending, self.auth)

            # Render the pending tool calls as a small panel each, so the user
            # sees exactly what the model is about to run.
            for call in pending:
                self._print_tool_call_header(call)

            denied: list[str] = []
            for call in blocking:
                allow = self._ask_auth(call.name, call.tier, call.args)
                if call.tier == "confirm_once":
                    self.auth.remember(call.name, allow)
                if not allow:
                    denied.append(call.name)

            if denied:
                self._inject_denials(messages, denied)
                input_payload = None

    # -- streaming ----------------------------------------------------------

    def _stream_until_interrupt(self, input_payload: dict | None) -> None:
        """Stream the agent. Renders assistant tokens as live Markdown and tool
        results in their own Panels — exactly once each.
        """
        seen_tool_ids: set[str] = set()
        buffer: str = ""
        live: Live | None = None
        spinner_shown = True

        def start_or_update_live() -> None:
            """Open the Markdown live region (or update it) with the current buffer."""
            nonlocal live, spinner_shown
            if spinner_shown:
                # First assistant token — make room for the Live region.
                spinner_shown = False
            if live is None:
                live = Live(
                    Markdown(buffer or " "),
                    console=console,
                    refresh_per_second=12,
                    transient=False,
                    auto_refresh=False,
                )
                live.start()
            live.update(Markdown(buffer or " "), refresh=True)

        def close_live() -> None:
            """Commit the current Markdown region to scrollback and reset."""
            nonlocal live, buffer
            if live is not None:
                live.update(Markdown(buffer), refresh=True)
                live.stop()
                live = None
            buffer = ""

        status = console.status("[dim]thinking…[/dim]", spinner="dots")
        status.start()

        try:
            events = self.agent.stream(
                input_payload,
                self.config,
                stream_mode=["messages", "values"],
            )
            for kind, payload in events:
                if kind == "messages":
                    chunk, _meta = payload
                    if not isinstance(chunk, (AIMessage, AIMessageChunk)):
                        continue
                    text = _extract_text(chunk.content)
                    if not text:
                        continue
                    if spinner_shown:
                        status.stop()
                    buffer += text
                    start_or_update_live()

                elif kind == "values":
                    messages = payload.get("messages", [])
                    if not messages:
                        continue
                    last = messages[-1]
                    if not isinstance(last, ToolMessage):
                        continue
                    tool_id = getattr(last, "tool_call_id", None) or id(last)
                    if tool_id in seen_tool_ids:
                        continue
                    seen_tool_ids.add(tool_id)
                    # Close the in-flight assistant block before printing the
                    # tool result so they don't fight for the same screen region.
                    close_live()
                    if spinner_shown:
                        status.stop()
                        spinner_shown = False
                    _render_tool_result(getattr(last, "name", "tool"), last.content)
        except Exception as e:
            close_live()
            if spinner_shown:
                status.stop()
            console.print(
                Panel(
                    Text.from_markup(f"[red]{type(e).__name__}: {e}[/red]"),
                    title="[red]Agent error[/red]",
                    title_align="left",
                    border_style="red",
                )
            )
        finally:
            close_live()
            if spinner_shown:
                # Stream ended before any AI tokens were produced (e.g. agent
                # paused at the tools node immediately). Tear the spinner down.
                status.stop()

    def _print_tool_call_header(self, call) -> None:
        """Render the dimmed ``→ tool_name(args)`` line that introduces a tool call."""
        style = _TIER_STYLE.get(call.tier, "dim")
        args_summary = _render_tool_args(call.args)
        suffix = f"({args_summary})" if args_summary else "()"
        console.print(f"[{style}]→ {call.name}{suffix}[/{style}]")

    def _record_last_ai_message(self, state) -> None:
        messages = state.values.get("messages", [])
        for m in reversed(messages):
            if isinstance(m, AIMessage) and m.content:
                content = m.content if isinstance(m.content, str) else str(m.content)
                self.transcript.append({"role": "assistant", "content": content})
                return

    def _inject_denials(self, messages: list, denied: list[str]) -> None:
        """Update the graph state with synthetic ToolMessages for refused calls."""
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", []) or []
        denial_messages = [
            ToolMessage(
                content=(
                    "The user declined to run this tool. Do not retry; explain the "
                    "situation and offer an alternative or ask what they'd like to do."
                ),
                tool_call_id=call["id"],
                name=call["name"],
            )
            for call in tool_calls
            if call.get("name") in denied
        ]
        if denial_messages:
            self.agent.update_state(self.config, {"messages": denial_messages})

    # -- authorization UI --------------------------------------------------

    def _ask_auth(self, tool_name: str, tier: str, args: dict | None = None) -> bool:
        note = {
            "confirm_once": "Decision remembered for this session.",
            "confirm_each": "Asked every time (writes a file).",
        }.get(tier, "")
        args_summary = _render_tool_args(args or {}) or "(no arguments)"

        lines: list[str] = [
            f"[bold]{tool_name}[/bold]",
            f"[dim]{args_summary}[/dim]",
        ]
        if note:
            lines.append(f"[dim]{note}[/dim]")
        console.print(
            Panel(
                "\n".join(lines),
                title="[yellow]⏵ Tool authorization[/yellow]",
                title_align="left",
                border_style="yellow",
                padding=(0, 1),
            )
        )
        answer = Prompt.ask("Allow", choices=["y", "n"], default="y")
        return answer == "y"


def _extract_text(content) -> str:
    """Pull the text payload out of an ``AIMessageChunk.content``.

    OpenAI streams give us ``str`` chunks. Anthropic streams give us a list of
    ``{"type": "text", "text": "..."}`` dicts; we concatenate the text parts.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    return ""


# ---------------------------------------------------------------------------
# Slash command handling
# ---------------------------------------------------------------------------


def _handle_slash(cmd: str, session: ChatSession) -> bool:
    """Process a slash command. Returns True if the REPL should exit."""
    parts = cmd.strip().split(maxsplit=1)
    head = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if head in {"/quit", "/exit", "/q"}:
        return True
    if head == "/help":
        console.print(Markdown(_HELP_TEXT))
        return False
    if head == "/clear":
        session.reset()
        console.print("[dim]Conversation reset.[/dim]")
        return False
    if head == "/menu":
        from seo_bhishma.cli.app import menu

        ctx = click.get_current_context(silent=True)
        if ctx is not None:
            ctx.invoke(menu)
        else:
            console.print("[yellow][!] /menu only works inside the seo-bhishma CLI.[/yellow]")
        return False
    if head == "/tools":
        _print_tool_catalogue()
        return False
    if head == "/model":
        if not arg:
            console.print(f"[yellow]Current model: {session.model or 'default'}[/yellow]")
            return False
        session.swap_model(arg)
        console.print(f"[green]Switched to model: {arg}[/green]")
        return False
    if head == "/save":
        target = arg or f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        _save_transcript(session, target)
        console.print(f"[green]Transcript saved to {target}[/green]")
        return False

    console.print(f"[yellow]Unknown command: {head}. Try /help.[/yellow]")
    return False


def _print_tool_catalogue() -> None:
    table = Table(title="Available tools", header_style="bold")
    table.add_column("name", style="cyan", no_wrap=True)
    table.add_column("auth", no_wrap=True)
    table.add_column("description")
    for t in ALL_TOOLS:
        tier = (t.metadata or {}).get("auth_tier", "?")
        style = _TIER_STYLE.get(tier, "")
        first_line = (t.description or "").splitlines()[0]
        table.add_row(t.name, f"[{style}]{tier}[/{style}]", first_line)
    console.print(table)


def _save_transcript(session: ChatSession, path: str) -> None:
    out_path = Path(path)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# SEO Bhishma chat — {datetime.now().isoformat()}\n\n")
        for entry in session.transcript:
            role = entry["role"]
            f.write(f"## {role}\n\n{entry['content']}\n\n")


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command()
@click.option("--model", default=None, help="Override LLM model (e.g. gpt-4o, claude-sonnet-4-5).")
def chat(model: str | None) -> None:
    """Chat with the SEO Bhishma AI agent."""
    _silence_noisy_loggers()
    try:
        session = ChatSession(model=model)
    except LlmConfigError as e:
        console.print(f"[bold red]{e}[/bold red]")
        return

    provider = session.settings.resolve_provider()
    resolved_model = session.model or session.settings.resolve_model(provider)
    console.print(
        tool_panel(
            f"{CLI_NAME} chat",
            f"[bold]{resolved_model}[/bold] ([cyan]{provider}[/cyan]) • v{CLI_VERSION}\n"
            "Ask me about SEO. I'll pick the right tool and run it for you.\n"
            "[dim]/help for commands · /quit to exit[/dim]",
        )
    )

    while True:
        try:
            user_input = Prompt.ask("[bold green]you[/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.startswith("/"):
            if _handle_slash(user_input, session):
                break
            continue

        try:
            session.turn(user_input)
        except KeyboardInterrupt:
            console.print("\n[yellow][!] Interrupted current turn. Conversation kept.[/yellow]")
            continue
        except Exception as e:
            console.print(f"[bold red][-] Turn failed: {e}[/bold red]")

    console.print("[bold red]Goodbye![/bold red]")
