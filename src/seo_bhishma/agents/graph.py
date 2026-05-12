"""LangGraph ReAct agent for the SEO Bhishma chat REPL.

Builds on top of :func:`langgraph.prebuilt.create_react_agent`, layering:

* A persisted ``InMemorySaver`` so the conversation can be resumed across
  turns by passing the same ``thread_id``.
* ``interrupt_before=["tools"]`` so the REPL can authorize tool calls per the
  tier on each tool's metadata (see :mod:`seo_bhishma.agents.tools`).
* :class:`ToolAuthSession` — a small object the REPL uses to remember
  per-session ``confirm_once`` approvals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from seo_bhishma.agents.llm import get_llm
from seo_bhishma.agents.prompts import SYSTEM_PROMPT
from seo_bhishma.agents.tools import ALL_TOOLS, get_auth_tier
from seo_bhishma.config.settings import Settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel


def _today() -> str:
    return date.today().isoformat()


def build_agent(
    settings: Settings | None = None,
    *,
    model: str | None = None,
    llm: BaseChatModel | None = None,
    interrupt_before_tools: bool = True,
):
    """Construct a fresh LangGraph ReAct agent bound to all SEO tools.

    Args:
        settings: Optional ``Settings``. Defaults to ``Settings()``.
        model: Override the model name.
        llm: Pre-built chat model. Wins over ``model``. Useful for tests.
        interrupt_before_tools: If True (default), pause before each tool call
            so the REPL can authorize it. Tests can pass False to run
            uninterrupted.

    Returns:
        A compiled LangGraph runnable. Use ``.invoke({"messages": [...]})`` for
        a single response or ``.stream(...)`` / ``.astream(...)`` for tokens.
    """
    settings = settings or Settings()
    llm = llm or get_llm(settings, model=model)

    kwargs: dict = {
        "model": llm,
        "tools": ALL_TOOLS,
        "prompt": SYSTEM_PROMPT.format(today=_today()),
        "checkpointer": InMemorySaver(),
    }
    if interrupt_before_tools:
        kwargs["interrupt_before"] = ["tools"]

    return create_react_agent(**kwargs)


# ---------------------------------------------------------------------------
# Tool-call inspection + authorization session
# ---------------------------------------------------------------------------


@dataclass
class PendingToolCall:
    """A tool call awaiting authorization."""

    name: str
    tier: str  # "auto" | "confirm_once" | "confirm_each"
    args: dict


@dataclass
class ToolAuthSession:
    """Track per-session authorization decisions for ``confirm_once`` tools.

    The REPL constructs one of these at the start of a chat and re-uses it
    across turns. ``approved`` records names the user has already said "yes"
    to; ``denied`` records names refused (we won't re-prompt within the
    session, but the LLM is told the call was skipped).
    """

    approved: set[str] = field(default_factory=set)
    denied: set[str] = field(default_factory=set)

    def remember(self, tool_name: str, allow: bool) -> None:
        if allow:
            self.approved.add(tool_name)
        else:
            self.denied.add(tool_name)

    def decision(self, tool_name: str) -> bool | None:
        """Return cached decision: True / False / None (no decision yet)."""
        if tool_name in self.approved:
            return True
        if tool_name in self.denied:
            return False
        return None


def classify_tool_calls(messages: list) -> list[PendingToolCall]:
    """Inspect the latest assistant message for tool calls and tag them.

    Returns a list of :class:`PendingToolCall` for any tool calls in the most
    recent ``AIMessage``. Empty list if the last message isn't an assistant
    turn or has no tool calls.
    """
    if not messages:
        return []
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    return [
        PendingToolCall(
            name=call["name"],
            tier=get_auth_tier(call["name"]),
            args=call.get("args", {}),
        )
        for call in tool_calls
    ]


def needs_user_confirmation(
    calls: list[PendingToolCall], session: ToolAuthSession
) -> list[PendingToolCall]:
    """Return the subset of pending calls that should block the REPL for input.

    Logic:

    * ``tier == "auto"`` never blocks.
    * ``tier == "confirm_once"`` blocks only the first time per session per
      tool name. After the user decides, the answer is cached on ``session``.
    * ``tier == "confirm_each"`` always blocks (file-write tools).
    """
    blocking: list[PendingToolCall] = []
    for call in calls:
        if call.tier == "auto":
            continue
        if call.tier == "confirm_once" and session.decision(call.name) is not None:
            continue
        blocking.append(call)
    return blocking


def _smoke_test() -> None:
    """Minimal end-to-end check (requires an API key)."""
    from langchain_core.messages import HumanMessage

    agent = build_agent(interrupt_before_tools=False)
    config = {"configurable": {"thread_id": "smoke-test"}}
    final = agent.invoke(
        {"messages": [HumanMessage(content="What DNS records does example.com have?")]},
        config=config,
    )
    for m in final["messages"]:
        prefix = type(m).__name__
        content = (m.content or "")[:200]
        print(f"[{prefix}] {content}")


if __name__ == "__main__":
    _smoke_test()
