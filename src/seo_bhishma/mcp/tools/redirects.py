"""MCP tools for URL redirect mapping."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register redirect tools with the MCP server."""

    @mcp.tool()
    def map_redirect_urls(
        source_urls: list[str],
        dest_urls: list[str],
        use_web_content: bool = False,
        rate_limit: float = 0,
        max_workers: int = 10,
        spacy_model: str = "en_core_web_sm",
    ) -> list[dict]:
        """Map source URLs to best-matching destination URLs using NLP similarity.

        Uses TF-IDF on URL slugs with spaCy lemmatization, with optional web content
        comparison for low-confidence matches.

        Args:
            source_urls: URLs that need redirects (old URLs).
            dest_urls: Candidate destination URLs (new URLs).
            use_web_content: If True, fetch page content for low-confidence matches.
            rate_limit: Delay in seconds between web content requests.
            max_workers: Number of parallel workers.
            spacy_model: spaCy model for NLP processing.

        Returns:
            List of mapping results with source, destination, confidence_score, and remark.
        """
        from seo_bhishma.core.redirection_genius import map_urls

        results = map_urls(
            source_urls,
            dest_urls,
            use_web_content=use_web_content,
            rate_limit=rate_limit,
            max_workers=max_workers,
            spacy_model=spacy_model,
        )
        return [r.model_dump() for r in results]
