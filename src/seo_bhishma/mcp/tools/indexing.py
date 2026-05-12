"""MCP tools for indexing status checks."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register indexing tools with the MCP server."""

    @mcp.tool()
    def check_indexing_status(
        url: str,
        method: str = "htmlsession",
        rate_limit: float = 0,
        headless: bool = False,
    ) -> dict:
        """Check if a URL is indexed in Google.

        Args:
            url: URL to check indexing status for.
            method: Check method - "htmlsession" or "playwright".
            rate_limit: Delay in seconds after the check.
            headless: Run browser in headless mode (playwright only).

        Returns:
            Dict with url, status, and proxy_used.
        """
        from seo_bhishma.core.index_spy import check_indexing_status as _check
        from seo_bhishma.models.index_spy import CheckMethod

        result = _check(
            url,
            method=CheckMethod(method),
            rate_limit=rate_limit,
            headless=headless,
        )
        return result.model_dump()

    @mcp.tool()
    def batch_check_indexing(
        urls: list[str],
        method: str = "htmlsession",
        rate_limit: float = 0,
        headless: bool = False,
        max_captcha_retries: int = 3,
    ) -> dict:
        """Check indexing status for multiple URLs.

        Args:
            urls: List of URLs to check.
            method: Check method - "htmlsession" or "playwright".
            rate_limit: Delay between checks in seconds.
            headless: Run browser in headless mode (playwright only).
            max_captcha_retries: Max CAPTCHA failures before stopping.

        Returns:
            Dict with results list and summary counts.
        """
        from seo_bhishma.core.index_spy import batch_check_indexing as _batch
        from seo_bhishma.models.index_spy import CheckMethod

        result = _batch(
            urls,
            method=CheckMethod(method),
            rate_limit=rate_limit,
            headless=headless,
            max_captcha_retries=max_captcha_retries,
        )
        return result.model_dump()
