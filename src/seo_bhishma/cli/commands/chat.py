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
import uuid
from datetime import datetime
from pathlib import Path

import click
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

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


def _render_tool_result(content: str) -> None:
    """Try to render a tool result as a Rich table; fall back to syntax-highlighted JSON."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except (json.JSONDecodeError, TypeError):
        console.print(Panel(content, border_style="dim", title="tool result", title_align="left"))
        return

    # Special-cases for common tool result shapes
    if isinstance(data, dict):
        if "head" in data and isinstance(data["head"], list) and data["head"]:
            _render_table(data["head"], title="head")
            extras = {k: v for k, v in data.items() if k != "head"}
            if extras:
                _render_kv(extras)
            return
        if "sample_urls" in data and isinstance(data["sample_urls"], list):
            console.print(
                Panel(
                    "\n".join(data["sample_urls"][:20]),
                    title=f"sample of {len(data['sample_urls'])} URLs",
                    border_style="dim",
                )
            )
            extras = {k: v for k, v in data.items() if k != "sample_urls"}
            if extras:
                _render_kv(extras)
            return
        _render_kv(data)
        return

    if isinstance(data, list) and data and isinstance(data[0], dict):
        _render_table(data, title="tool result")
        return

    pretty = json.dumps(data, indent=2, default=str)
    console.print(Syntax(pretty, "json", theme="ansi_dark", line_numbers=False))


def _render_kv(data: dict) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, default=str)[:160]
        table.add_row(str(k), str(v))
    console.print(table)


def _render_table(rows: list[dict], title: str = "") -> None:
    columns = list(rows[0].keys())
    table = Table(title=title or None, header_style="bold")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[str(row.get(c, "")) for c in columns])
    console.print(table)


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
            # Stream this segment of the run.
            self._stream_until_interrupt(input_payload)
            input_payload = None  # subsequent loops resume from checkpoint

            state = self.agent.get_state(self.config)
            if "tools" not in (state.next or ()):
                # Run is done.
                self._record_last_ai_message(state)
                return

            messages = state.values.get("messages", [])
            pending = classify_tool_calls(messages)
            blocking = needs_user_confirmation(pending, self.auth)

            for call in pending:
                style = _TIER_STYLE.get(call.tier, "")
                console.print(
                    f"[{style}][tool] {call.name}({_render_tool_args(call.args)})[/{style}]"
                )

            # Authorize the blocking calls.
            denied: list[str] = []
            for call in blocking:
                allow = self._ask_auth(call.name, call.tier)
                if call.tier == "confirm_once":
                    self.auth.remember(call.name, allow)
                if not allow:
                    denied.append(call.name)

            if denied:
                # Inject synthetic ToolMessages so the LLM knows the calls were
                # refused, then continue the run.
                self._inject_denials(messages, denied)
                input_payload = None  # state already updated

    # -- streaming ----------------------------------------------------------

    def _stream_until_interrupt(self, input_payload: dict | None) -> None:
        """Stream the agent, printing token-level updates for the assistant turn."""
        printed_any_chunk = False
        with console.status("[dim]thinking…[/dim]", spinner="dots"):
            try:
                events = self.agent.stream(
                    input_payload,
                    self.config,
                    stream_mode=["messages", "values"],
                )
                for kind, payload in events:
                    if kind == "messages":
                        msg_chunk, _meta = payload
                        text = getattr(msg_chunk, "content", "") or ""
                        if isinstance(text, list):
                            text = "".join(
                                part.get("text", "")
                                for part in text
                                if isinstance(part, dict)
                            )
                        if text and isinstance(msg_chunk, AIMessage):
                            if not printed_any_chunk:
                                console.print()
                                printed_any_chunk = True
                            console.print(text, end="", soft_wrap=True)
                    elif kind == "values":
                        # On tool messages, render the latest tool result.
                        messages = payload.get("messages", [])
                        if messages and isinstance(messages[-1], ToolMessage):
                            _render_tool_result(messages[-1].content)
            except Exception as e:
                console.print(f"\n[bold red][-] Agent error: {e}[/bold red]")

        if printed_any_chunk:
            console.print()  # trailing newline after streamed tokens

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

    def _ask_auth(self, tool_name: str, tier: str) -> bool:
        note = {
            "confirm_once": "(decision remembered for this session)",
            "confirm_each": "(asked every time it writes a file)",
        }.get(tier, "")
        prompt = f"[bold]Allow `{tool_name}`?[/bold] {note}"
        answer = Prompt.ask(prompt, choices=["y", "n"], default="y")
        return answer == "y"


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
            f"AI-native SEO assistant • provider={provider} • model={resolved_model}\n"
            f"v{CLI_VERSION} — type [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit.",
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
