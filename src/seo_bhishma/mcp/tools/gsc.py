"""MCP tools for Google Search Console data extraction."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register GSC tools with the MCP server."""

    @mcp.tool()
    def gsc_list_sites(credentials_path: str, token_path: str = "token.pickle") -> list[dict]:
        """List all sites available in a Google Search Console account.

        Args:
            credentials_path: Path to the OAuth credentials JSON file.
            token_path: Path to the authentication token file.

        Returns:
            List of site entries with siteUrl and permissionLevel.
        """
        from seo_bhishma.core.gsc_probe import authenticate_gsc, list_sites

        service = authenticate_gsc(credentials_path, token_path)
        return list_sites(service)

    @mcp.tool()
    def gsc_fetch_search_analytics(
        credentials_path: str,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: list[str] | None = None,
        row_limit: int = 25000,
        search_type: str = "web",
        filters: list[dict] | None = None,
        filter_group_operator: str = "and",
        start_row: int = 0,
        token_path: str = "token.pickle",
    ) -> dict:
        """Fetch search analytics data from Google Search Console.

        Args:
            credentials_path: Path to the OAuth credentials JSON file.
            site_url: Site URL as registered in GSC.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            dimensions: Dimensions to group by (e.g., ["date", "query", "page"]).
            row_limit: Maximum rows to fetch.
            search_type: Search type (web, image, video, news).
            filters: Dimension filters - list of dicts with keys
                ``dimension``, ``operator``, ``expression``.
            filter_group_operator: "and" or "or" between filters.
            start_row: Resume from this row offset (for checkpoint/resume).
            token_path: Path to the authentication token file.

        Returns:
            Dict with rows, dimensions, and total_rows.
        """
        from seo_bhishma.core.gsc_probe import authenticate_gsc, fetch_search_analytics
        from seo_bhishma.models.gsc_probe import SearchAnalyticsFilter

        service = authenticate_gsc(credentials_path, token_path)
        filter_models = [SearchAnalyticsFilter(**f) for f in filters] if filters else None
        result = fetch_search_analytics(
            service, site_url, start_date, end_date,
            dimensions=dimensions,
            row_limit=row_limit,
            search_type=search_type,
            filters=filter_models,
            filter_group_operator=filter_group_operator,
            start_row=start_row,
        )
        return result.model_dump()

    @mcp.tool()
    def gsc_fetch_search_analytics_chunked(
        credentials_path: str,
        site_url: str,
        start_date: str,
        end_date: str,
        chunk_days: int = 30,
        dimensions: list[str] | None = None,
        search_type: str = "web",
        token_path: str = "token.pickle",
    ) -> dict:
        """Fetch GSC search analytics in date chunks (avoids the 25k-row cap per query).

        Args:
            credentials_path: Path to the OAuth credentials JSON file.
            site_url: Site URL as registered in GSC.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            chunk_days: Days per chunk (default 30).
            dimensions: Dimensions to group by.
            search_type: Search type.
            token_path: Path to the authentication token file.

        Returns:
            Dict with rows, dimensions, and total_rows aggregated across chunks.
        """
        from seo_bhishma.core.gsc_probe import (
            authenticate_gsc,
            fetch_search_analytics_chunked,
        )

        service = authenticate_gsc(credentials_path, token_path)
        result = fetch_search_analytics_chunked(
            service, site_url, start_date, end_date,
            chunk_days=chunk_days,
            dimensions=dimensions,
            search_type=search_type,
        )
        return result.model_dump()

    @mcp.tool()
    def gsc_fetch_sitemaps(
        credentials_path: str,
        site_url: str,
        token_path: str = "token.pickle",
    ) -> list[dict]:
        """Fetch sitemap information from Google Search Console.

        Args:
            credentials_path: Path to the OAuth credentials JSON file.
            site_url: Site URL as registered in GSC.
            token_path: Path to the authentication token file.

        Returns:
            List of sitemap info dicts with path, last_downloaded, and sitemap_type.
        """
        from seo_bhishma.core.gsc_probe import authenticate_gsc, fetch_sitemaps

        service = authenticate_gsc(credentials_path, token_path)
        results = fetch_sitemaps(service, site_url)
        return [s.model_dump() for s in results]

    @mcp.tool()
    def gsc_inspect_urls(
        credentials_path: str,
        site_url: str,
        urls: list[str],
        token_path: str = "token.pickle",
    ) -> list[dict]:
        """Inspect URLs using the GSC URL Inspection API.

        Args:
            credentials_path: Path to the OAuth credentials JSON file.
            site_url: Site URL as registered in GSC.
            urls: List of URLs to inspect.
            token_path: Path to the authentication token file.

        Returns:
            List of URL inspection results.
        """
        from seo_bhishma.core.gsc_probe import authenticate_gsc, fetch_url_inspection

        service = authenticate_gsc(credentials_path, token_path)
        results = fetch_url_inspection(service, site_url, urls)
        return [r.model_dump() for r in results]

    @mcp.tool()
    def gsc_get_available_dates(
        credentials_path: str,
        site_url: str,
        token_path: str = "token.pickle",
    ) -> dict:
        """Get the earliest and latest available dates for a site in GSC.

        Args:
            credentials_path: Path to the OAuth credentials JSON file.
            site_url: Site URL as registered in GSC.
            token_path: Path to the authentication token file.

        Returns:
            Dict with start_date and end_date.
        """
        from seo_bhishma.core.gsc_probe import authenticate_gsc, get_available_dates

        service = authenticate_gsc(credentials_path, token_path)
        start, end = get_available_dates(service, site_url)
        return {"start_date": start, "end_date": end}
