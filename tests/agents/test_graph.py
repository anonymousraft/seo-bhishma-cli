"""Tests for the LangGraph agent assembly + tool authorization session.

Per-prompt tool-selection accuracy is *not* tested here because that would
require a real LLM call. Tests focus on the deterministic pieces: graph
compilation with a fake LLM, the tool-call classifier, and the
:class:`ToolAuthSession` state machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from seo_bhishma.agents.graph import (
    PendingToolCall,
    ToolAuthSession,
    build_agent,
    classify_tool_calls,
    needs_user_confirmation,
)


class _ToolBindableFake(FakeListChatModel):
    """``FakeListChatModel`` + a no-op ``bind_tools`` so ``create_react_agent`` accepts it."""

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):  # type: ignore[override]
        return self


def _fake(responses: list[str]) -> _ToolBindableFake:
    return _ToolBindableFake(responses=responses)


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------


def test_build_agent_compiles_with_fake_llm() -> None:
    agent = build_agent(llm=_fake(["ok"]), interrupt_before_tools=False)
    config = {"configurable": {"thread_id": "t-1"}}
    final = agent.invoke({"messages": [HumanMessage(content="hi")]}, config=config)
    assert len(final["messages"]) >= 2


def test_build_agent_respects_interrupt_flag() -> None:
    """``interrupt_before_tools=True`` shouldn't pause when no tool calls are emitted."""
    agent = build_agent(llm=_fake(["no tool needed"]), interrupt_before_tools=True)
    config = {"configurable": {"thread_id": "t-2"}}
    final = agent.invoke({"messages": [HumanMessage(content="hello")]}, config=config)
    # No tool call → no interrupt → run completes.
    state = agent.get_state(config)
    assert "tools" not in (state.next or ())
    assert isinstance(final["messages"][-1], AIMessage)


# ---------------------------------------------------------------------------
# classify_tool_calls
# ---------------------------------------------------------------------------


def test_classify_tool_calls_empty_when_no_messages() -> None:
    assert classify_tool_calls([]) == []


def test_classify_tool_calls_empty_when_no_tool_calls() -> None:
    msg = AIMessage(content="just words")
    assert classify_tool_calls([msg]) == []


def test_classify_tool_calls_tags_each_call_with_tier() -> None:
    msg = AIMessage(
        content="",
        tool_calls=[
            {"id": "a", "name": "get_dns_records", "args": {"domain": "example.com"}},
            {"id": "b", "name": "generate_sitemap", "args": {"urls": []}},
            {"id": "c", "name": "gsc_fetch_search_analytics", "args": {}},
        ],
    )
    result = classify_tool_calls([msg])
    assert [(c.name, c.tier) for c in result] == [
        ("get_dns_records", "auto"),
        ("generate_sitemap", "confirm_each"),
        ("gsc_fetch_search_analytics", "confirm_once"),
    ]


def test_classify_tool_calls_unknown_defaults_to_confirm_each() -> None:
    msg = AIMessage(
        content="",
        tool_calls=[{"id": "x", "name": "nope", "args": {}}],
    )
    [call] = classify_tool_calls([msg])
    assert call.tier == "confirm_each"


# ---------------------------------------------------------------------------
# ToolAuthSession + needs_user_confirmation
# ---------------------------------------------------------------------------


def test_auth_session_starts_empty() -> None:
    session = ToolAuthSession()
    assert session.decision("any_tool") is None


def test_auth_session_remembers_approval() -> None:
    session = ToolAuthSession()
    session.remember("gsc_fetch_search_analytics", True)
    assert session.decision("gsc_fetch_search_analytics") is True


def test_auth_session_remembers_denial() -> None:
    session = ToolAuthSession()
    session.remember("find_subdomains", False)
    assert session.decision("find_subdomains") is False


def test_needs_user_confirmation_auto_never_blocks() -> None:
    calls = [PendingToolCall("get_dns_records", "auto", {"domain": "x"})]
    assert needs_user_confirmation(calls, ToolAuthSession()) == []


def test_needs_user_confirmation_confirm_once_blocks_until_remembered() -> None:
    calls = [PendingToolCall("gsc_fetch_search_analytics", "confirm_once", {})]
    session = ToolAuthSession()
    assert needs_user_confirmation(calls, session) == calls
    session.remember("gsc_fetch_search_analytics", True)
    assert needs_user_confirmation(calls, session) == []


def test_needs_user_confirmation_confirm_each_always_blocks() -> None:
    calls = [PendingToolCall("generate_sitemap", "confirm_each", {"urls": []})]
    session = ToolAuthSession()
    session.remember("generate_sitemap", True)  # even after a previous yes
    blocking = needs_user_confirmation(calls, session)
    assert blocking == calls


def test_needs_user_confirmation_mixes_tiers() -> None:
    calls = [
        PendingToolCall("get_dns_records", "auto", {}),
        PendingToolCall("gsc_fetch_search_analytics", "confirm_once", {}),
        PendingToolCall("generate_sitemap", "confirm_each", {}),
    ]
    session = ToolAuthSession()
    session.remember("gsc_fetch_search_analytics", True)
    blocking = needs_user_confirmation(calls, session)
    assert [c.name for c in blocking] == ["generate_sitemap"]


# ---------------------------------------------------------------------------
# Preferences (covered here because there's no separate test file)
# ---------------------------------------------------------------------------


def test_preferences_roundtrip(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Save → load round-trip via the SEO_BHISHMA_HOME sandbox env var."""
    from seo_bhishma.cli.preferences import (
        Preferences,
        load_preferences,
        save_preferences,
    )

    monkeypatch.setenv("SEO_BHISHMA_HOME", str(tmp_path))
    assert load_preferences() is None  # no file yet
    save_preferences(Preferences(default_interface="menu"))
    loaded = load_preferences()
    assert loaded is not None
    assert loaded.default_interface == "menu"
    save_preferences(Preferences(default_interface="chat"))
    assert load_preferences().default_interface == "chat"
