"""SEO Bhishma MCP Server - Exposes SEO tools via the Model Context Protocol."""

from fastmcp import FastMCP

from seo_bhishma.core._logging import setup_logging
from seo_bhishma.mcp.resources import sitemap as sitemap_resources
from seo_bhishma.mcp.tools import (
    backlinks,
    cannibalization,
    domain,
    gsc,
    indexing,
    keywords,
    redirects,
    sitemaps,
)

mcp = FastMCP(
    "SEO Bhishma",
    instructions=(
        "Comprehensive SEO toolkit with backlink checking, sitemap parsing, "
        "keyword clustering, indexing checks, domain analysis, redirect mapping, "
        "GSC data extraction, and cannibalization detection."
    ),
)

# Register all tool modules
backlinks.register(mcp)
sitemaps.register(mcp)
indexing.register(mcp)
keywords.register(mcp)
gsc.register(mcp)
redirects.register(mcp)
domain.register(mcp)
cannibalization.register(mcp)

# Register resources
sitemap_resources.register(mcp)


def main():
    """Entry point for the MCP server (stdio transport)."""
    setup_logging()
    mcp.run()


if __name__ == "__main__":
    main()
