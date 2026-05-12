"""MCP tools for URL cannibalization detection."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register cannibalization tools with the MCP server."""

    @mcp.tool()
    def detect_cannibalization(
        file_path: str,
        exact_match_threshold: float = 0.2,
        impression_share_threshold: float = 0.7,
        click_share_threshold: float = 0.2,
        query_share_threshold: float = 25.0,
        use_slug_similarity: bool = False,
        slug_similarity_threshold: float = 0.5,
        use_semantic_check: bool = False,
    ) -> dict:
        """Detect URL cannibalization from GSC data.

        Analyzes a CSV file with Google Search Console data (columns: page, query,
        clicks, impressions, ctr, position) to identify URLs competing for the same
        keywords.

        Args:
            file_path: Path to the GSC data CSV file.
            exact_match_threshold: Threshold for exact match query ratio (0-1).
            impression_share_threshold: Threshold for impression share (0-1).
            click_share_threshold: Threshold for click share (0-1).
            query_share_threshold: Threshold for query share percentage.
            use_slug_similarity: Enable URL slug similarity check.
            slug_similarity_threshold: Threshold for URL slug similarity (0-1).
            use_semantic_check: Enable semantic similarity check (requires sentence-transformers).

        Returns:
            Dict with entries (list of cannibalization findings), total_clusters,
            and total_pages_analyzed.
        """
        from seo_bhishma.core.hannibal import detect_cannibalization as _detect
        from seo_bhishma.models.hannibal import CannibalizationConfig

        config = CannibalizationConfig(
            exact_match_threshold=exact_match_threshold,
            impression_share_threshold=impression_share_threshold,
            click_share_threshold=click_share_threshold,
            query_share_threshold=query_share_threshold,
            use_slug_similarity=use_slug_similarity,
            slug_similarity_threshold=slug_similarity_threshold,
            use_semantic_check=use_semantic_check,
        )

        report = _detect(file_path, config=config)
        return report.model_dump()
