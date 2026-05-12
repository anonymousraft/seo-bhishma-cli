"""MCP tools for sitemap operations."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register sitemap tools with the MCP server."""

    @mcp.tool()
    def download_parse_sitemap(
        sitemap_url: str,
        max_workers: int = 10,
    ) -> dict:
        """Download and parse a sitemap, including nested sitemaps.

        Args:
            sitemap_url: URL of the sitemap to download.
            max_workers: Number of parallel workers for parsing.

        Returns:
            Dict with urls (list of URL entries) and total_sitemaps_parsed count.
        """
        from seo_bhishma.core.site_mapper import download_and_parse_sitemap

        result = download_and_parse_sitemap(sitemap_url, max_workers=max_workers)
        if result is None:
            return {"error": "Failed to download or parse sitemap", "urls": [], "total_sitemaps_parsed": 0}
        return result.model_dump()

    @mcp.tool()
    def generate_sitemap(
        urls: list[str],
        priority: str = "",
        frequency: str = "",
        lastmod: str = "",
    ) -> str:
        """Generate a sitemap XML string from a list of URLs.

        Args:
            urls: List of URLs to include in the sitemap.
            priority: Default priority for all URLs (e.g., "0.8").
            frequency: Default change frequency (e.g., "weekly").
            lastmod: Default last modified date (e.g., "2024-01-01").

        Returns:
            Sitemap XML content as a string.
        """
        from seo_bhishma.core.sitemap_generator import generate_sitemap as _gen

        content = _gen(
            urls,
            priority=priority or None,
            frequency=frequency or None,
            lastmod=lastmod or None,
        )
        return content.decode("utf-8")

    @mcp.tool()
    def generate_sitemap_index(sitemap_locs: list[str]) -> str:
        """Generate a sitemap index XML string.

        Args:
            sitemap_locs: List of sitemap URLs to include in the index.

        Returns:
            Sitemap index XML content as a string.
        """
        from seo_bhishma.core.sitemap_generator import generate_sitemap_index as _gen_idx

        content = _gen_idx(sitemap_locs)
        return content.decode("utf-8")

    @mcp.tool()
    def generate_nested_sitemaps(
        urls: list[str],
        output_dir: str,
        url_limit: int = 50000,
        priority: str = "",
        frequency: str = "",
        lastmod: str = "",
        compressed: bool = False,
    ) -> dict:
        """Generate multiple sitemap files plus an index, splitting large URL lists.

        Args:
            urls: All URLs to include.
            output_dir: Directory in which to write sitemap files.
            url_limit: Max URLs per individual sitemap (default 50000).
            priority: Default priority.
            frequency: Default change frequency.
            lastmod: Default last modified date.
            compressed: Gzip output files.

        Returns:
            Dict with sitemap_files and sitemap_index path.
        """
        from seo_bhishma.core.sitemap_generator import (
            generate_nested_sitemaps as _gen_nested,
        )

        files, index_path = _gen_nested(
            urls,
            output_dir,
            url_limit=url_limit,
            priority=priority or None,
            frequency=frequency or None,
            lastmod=lastmod or None,
            compressed=compressed,
        )
        return {"sitemap_files": files, "sitemap_index": index_path}

    @mcp.tool()
    def discover_sitemaps(domain: str) -> dict:
        """Discover sitemap URLs from a domain's robots.txt.

        Args:
            domain: Bare domain (no scheme).

        Returns:
            Dict with domain and discovered sitemap URLs.
        """
        from seo_bhishma.core.site_mapper import discover_sitemaps_from_robots

        sitemaps = discover_sitemaps_from_robots(domain)
        return {"domain": domain, "sitemaps": sitemaps}
