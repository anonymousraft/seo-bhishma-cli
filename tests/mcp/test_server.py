"""Tests for MCP server tool registration."""

import asyncio

import pytest


@pytest.fixture
def mcp_app():
    """Create MCP server instance for testing."""
    pytest.importorskip("fastmcp")
    from seo_bhishma.mcp.server import mcp
    return mcp


def test_mcp_server_has_tools(mcp_app):
    """Verify that all expected tools are registered."""
    tools = asyncio.run(mcp_app.list_tools())
    tool_names = {t.name for t in tools}

    expected_tools = {
        # backlinks
        "check_backlink",
        "batch_check_backlinks",
        # sitemaps
        "download_parse_sitemap",
        "generate_sitemap",
        "generate_sitemap_index",
        "generate_nested_sitemaps",
        "discover_sitemaps",
        # indexing
        "check_indexing_status",
        "batch_check_indexing",
        # keywords
        "estimate_embedding_tokens",
        "generate_keyword_embeddings",
        "cluster_keywords",
        "cluster_and_embed_keywords",
        # gsc
        "gsc_list_sites",
        "gsc_fetch_search_analytics",
        "gsc_fetch_search_analytics_chunked",
        "gsc_fetch_sitemaps",
        "gsc_inspect_urls",
        "gsc_get_available_dates",
        # redirects
        "map_redirect_urls",
        # domain
        "get_ip_address",
        "get_dns_records",
        "get_whois_info",
        "get_ip_details",
        "find_subdomains",
        "tech_stack_analysis",
        "fetch_robots_txt",
        "check_urls_against_robots",
        "validate_domain",
        "parse_robots_txt",
        "reverse_ip_lookup",
        "get_ssl_certificate",
        "get_security_headers",
        # cannibalization
        "detect_cannibalization",
    }

    for tool_name in expected_tools:
        assert tool_name in tool_names, f"Missing tool: {tool_name}"


def test_mcp_server_name(mcp_app):
    """Verify server name."""
    assert mcp_app.name == "SEO Bhishma"
