"""MCP tools for backlink checking."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register backlink tools with the MCP server."""

    @mcp.tool()
    def check_backlink(
        backlink_url: str,
        target_url: str,
        expected_anchor: str = "",
    ) -> dict:
        """Check if a backlink exists and verify its status.

        Args:
            backlink_url: The page that should contain the backlink.
            target_url: The URL the backlink should point to.
            expected_anchor: Expected anchor text (optional).

        Returns:
            Dict with status, anchor_status, link_exists, and actual_anchor_text.
        """
        from seo_bhishma.core.link_sniper import check_backlink as _check

        result = _check(backlink_url, target_url, expected_anchor)
        return result.model_dump()

    @mcp.tool()
    def batch_check_backlinks(
        checks: list[dict],
        max_workers: int = 10,
    ) -> list[dict]:
        """Check multiple backlinks in parallel.

        Args:
            checks: List of dicts with keys: backlink_url, target_url, expected_anchor (optional).
            max_workers: Number of parallel workers.

        Returns:
            List of backlink check results.
        """
        from seo_bhishma.core.link_sniper import batch_check_backlinks as _batch
        from seo_bhishma.models.link_sniper import BacklinkCheckRequest

        requests = [BacklinkCheckRequest(**c) for c in checks]
        results = _batch(requests, max_workers=max_workers)
        return [r.model_dump() for r in results]
