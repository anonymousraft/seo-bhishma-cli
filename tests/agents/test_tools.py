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
    """Cluster keyword tool should reject inputs >500 to prevent runaway API spend."""
    ck_tool = next(t for t in ALL_TOOLS if t.name == "cluster_keywords")
    keywords = [f"keyword {i}" for i in range(501)]
    with pytest.raises(ValueError, match="cap exceeded"):
        ck_tool.invoke({"keywords": keywords})


def test_cluster_keywords_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``SEO_BHISHMA_OPENAI_API_KEY`` the tool must error before calling OpenAI."""
    monkeypatch.delenv("SEO_BHISHMA_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("SEO_BHISHMA_OPENAI_API_KEY", "")
    ck_tool = next(t for t in ALL_TOOLS if t.name == "cluster_keywords")
    with pytest.raises(ValueError, match="SEO_BHISHMA_OPENAI_API_KEY"):
        ck_tool.invoke({"keywords": ["one", "two"]})
