"""Tests for LangChain tool wrappers in ``agents/tools.py``.

Verifies the catalog is complete and that each tool's authorization tier is
correctly tagged. Per-tool behavior is exercised through the underlying core
modules in ``tests/core/``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from seo_bhishma.agents.tools import ALL_TOOLS, get_auth_tier
from seo_bhishma.models.link_sniper import BacklinkCheckResult


def test_all_tools_have_unique_names() -> None:
    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"


def test_all_tools_have_descriptions() -> None:
    missing = [t.name for t in ALL_TOOLS if not (t.description or "").strip()]
    assert not missing, f"tools missing descriptions: {missing}"


def test_all_tools_have_auth_tier_metadata() -> None:
    tiers = {(t.metadata or {}).get("auth_tier") for t in ALL_TOOLS}
    assert tiers == {"auto", "confirm_once", "confirm_each"}


@pytest.mark.parametrize(
    "tool_name,expected_tier",
    [
        ("check_backlink", "auto"),
        ("get_dns_records", "auto"),
        ("check_indexing_status", "auto"),
        ("parse_sitemap", "auto"),
        ("gsc_list_sites", "auto"),
        ("gsc_fetch_search_analytics", "confirm_once"),
        ("batch_check_indexing", "confirm_once"),
        ("batch_check_backlinks", "confirm_once"),
        ("cluster_keywords", "confirm_once"),
        ("detect_cannibalization", "confirm_once"),
        ("map_redirect_urls", "confirm_once"),
        ("find_subdomains", "confirm_once"),
        ("generate_sitemap", "confirm_each"),
        ("generate_nested_sitemaps", "confirm_each"),
    ],
)
def test_tool_authorization_tiers(tool_name: str, expected_tier: str) -> None:
    assert get_auth_tier(tool_name) == expected_tier


def test_get_auth_tier_unknown_defaults_to_confirm_each() -> None:
    """Unknown tools fail closed (safer default)."""
    assert get_auth_tier("nonexistent_tool") == "confirm_each"


def test_silencer_suppresses_stdout_and_stderr_during_tool_calls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The wrapper installed in ``agents/tools.py`` must keep tool output off the user's terminal."""
    cb_tool = next(t for t in ALL_TOOLS if t.name == "check_backlink")

    def noisy(*args, **kwargs):
        import sys

        print("LEAK to stdout", flush=True)
        print("LEAK to stderr", file=sys.stderr, flush=True)
        return {"backlink_url": "x", "target_url": "y", "status": "Live",
                "anchor_status": "Present", "link_exists": "Yes"}

    with patch("seo_bhishma.agents.tools._ls.check_backlink", side_effect=noisy):
        cb_tool.invoke({"backlink_url": "x", "target_url": "y"})

    captured = capsys.readouterr()
    assert "LEAK" not in captured.out
    assert "LEAK" not in captured.err


def test_silencer_converts_exceptions_to_error_dict() -> None:
    """A core function that raises should surface as ``{"error": ...}`` not crash the agent."""
    cb_tool = next(t for t in ALL_TOOLS if t.name == "check_backlink")
    with patch(
        "seo_bhishma.agents.tools._ls.check_backlink",
        side_effect=RuntimeError("boom"),
    ):
        result = cb_tool.invoke({"backlink_url": "x", "target_url": "y"})
    assert result == {"error": "RuntimeError: boom"}


def test_check_backlink_tool_invokes_core() -> None:
    """The ``check_backlink`` tool wrapper delegates to ``core.link_sniper.check_backlink``."""
    cb_tool = next(t for t in ALL_TOOLS if t.name == "check_backlink")
    fake_result = BacklinkCheckResult(
        backlink_url="https://blog.example.com/post",
        target_url="https://example.com",
        status="Live",
        anchor_status="Present",
        link_exists="Yes",
        actual_anchor_text="example",
        http_status=200,
        rel_values=[],
        is_dofollow=True,
    )
    with patch("seo_bhishma.agents.tools._ls.check_backlink", return_value=fake_result) as mock:
        result = cb_tool.invoke(
            {
                "backlink_url": "https://blog.example.com/post",
                "target_url": "https://example.com",
                "expected_anchor": "example",
            }
        )
    mock.assert_called_once_with(
        "https://blog.example.com/post", "https://example.com", "example"
    )
    assert result["status"] == "Live"
    assert result["is_dofollow"] is True


def test_cluster_keywords_enforces_cap() -> None:
    """Cluster keyword tool should reject inputs >500 to prevent runaway API spend.

    The agent-facing tools are wrapped by ``_silence`` in ``agents/tools.py``,
    which converts any raised exception into a clean ``{"error": ...}`` dict
    so the model sees a structured result rather than a stack trace.
    """
    ck_tool = next(t for t in ALL_TOOLS if t.name == "cluster_keywords")
    keywords = [f"keyword {i}" for i in range(501)]
    result = ck_tool.invoke({"keywords": keywords})
    assert isinstance(result, dict)
    assert "error" in result
    assert "cap exceeded" in result["error"]


def test_cluster_keywords_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``SEO_BHISHMA_OPENAI_API_KEY`` the tool must error before calling OpenAI."""
    monkeypatch.delenv("SEO_BHISHMA_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SEO_BHISHMA_OPENAI_API_KEY", "")
    ck_tool = next(t for t in ALL_TOOLS if t.name == "cluster_keywords")
    result = ck_tool.invoke({"keywords": ["one", "two"]})
    assert isinstance(result, dict)
    assert "error" in result
    assert "SEO_BHISHMA_OPENAI_API_KEY" in result["error"]
