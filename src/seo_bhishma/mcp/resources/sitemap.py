"""MCP resource: fetch a sitemap's parsed URLs by URL.

Exposed as ``seo://sitemap/{sitemap_url}`` so MCP clients can browse sitemap
data without invoking a tool. Tools imperatively *do* work; resources
read state.
"""

from __future__ import annotations

import json
from urllib.parse import unquote

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register sitemap resources with the MCP server."""

    @mcp.resource("seo://sitemap/{sitemap_url}")
    def sitemap_resource(sitemap_url: str) -> str:
        """Return parsed URLs for the given sitemap (JSON).

        The path segment is URL-decoded so that callers may pass an encoded
        full sitemap URL.
        """
        from seo_bhishma.core.site_mapper import download_and_parse_sitemap

        decoded = unquote(sitemap_url)
        result = download_and_parse_sitemap(decoded)
        if result is None:
            return json.dumps({"error": "Failed to download or parse sitemap", "url": decoded})
        return result.model_dump_json()

    @mcp.resource("seo://robots/{domain}")
    def robots_resource(domain: str) -> str:
        """Return parsed robots.txt for the given domain (JSON)."""
        from seo_bhishma.core.domain_insight import fetch_robots_txt

        result = fetch_robots_txt(domain)
        if result is None:
            return json.dumps({"error": "robots.txt not found", "domain": domain})
        return result.model_dump_json()
