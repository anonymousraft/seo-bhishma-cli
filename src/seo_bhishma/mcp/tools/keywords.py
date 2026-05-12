"""MCP tools for keyword clustering."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register keyword tools with the MCP server."""

    @mcp.tool()
    def estimate_embedding_tokens(keywords: list[str]) -> dict:
        """Estimate OpenAI API token usage for keyword embedding generation.

        Args:
            keywords: List of keywords.

        Returns:
            Dict with estimated_tokens and estimated_cost_usd.
        """
        from seo_bhishma.core.keyword_sorcerer import estimate_token_usage

        tokens = estimate_token_usage(keywords)
        cost = (tokens / 1000) * 0.02
        return {"estimated_tokens": tokens, "estimated_cost_usd": round(cost, 4)}

    @mcp.tool()
    def generate_keyword_embeddings(
        keywords: list[str],
        api_key: str,
        model: str = "gpt-4o",
        rate_limit: float = 0.5,
    ) -> list[str]:
        """Generate descriptive sentence embeddings for keywords using OpenAI.

        Args:
            keywords: List of keywords to generate embeddings for.
            api_key: OpenAI API key.
            model: OpenAI model name.
            rate_limit: Delay between API calls in seconds.

        Returns:
            List of descriptive sentences (one per keyword).
        """
        from seo_bhishma.core.keyword_sorcerer import generate_embeddings

        return generate_embeddings(keywords, api_key, model=model, rate_limit=rate_limit)

    @mcp.tool()
    def cluster_keywords(
        keywords: list[str],
        embeddings: list[str],
        method: str = "kmeans",
        min_keywords_per_cluster: int = 4,
        max_keywords_per_cluster: int = 8,
    ) -> dict:
        """Cluster keywords using TF-IDF on descriptive sentences (legacy).

        Prefer ``cluster_and_embed_keywords`` for higher-quality results using
        real embedding vectors.

        Args:
            keywords: Original keywords list.
            embeddings: Descriptive sentences generated from keywords.
            method: Clustering algorithm - "kmeans", "agglomerative", "dbscan", or "spectral".
            min_keywords_per_cluster: Minimum keywords per cluster.
            max_keywords_per_cluster: Maximum keywords per cluster.

        Returns:
            Dict with keywords, labels, cluster_names, silhouette_score, and num_clusters.
        """
        from seo_bhishma.core.keyword_sorcerer import cluster_keywords as _cluster
        from seo_bhishma.models.keyword_sorcerer import ClusterMethod

        result = _cluster(
            keywords,
            embeddings,
            method=ClusterMethod(method),
            min_keywords_per_cluster=min_keywords_per_cluster,
            max_keywords_per_cluster=max_keywords_per_cluster,
        )
        return result.model_dump()

    @mcp.tool()
    def cluster_and_embed_keywords(
        keywords: list[str],
        api_key: str,
        embedding_model: str = "text-embedding-3-small",
        method: str = "agglomerative",
        min_keywords_per_cluster: int = 4,
        max_keywords_per_cluster: int = 8,
    ) -> dict:
        """Generate real embedding vectors then cluster with cosine distance.

        Preferred over the legacy TF-IDF-on-sentences flow. Returns the same
        ``ClusterResult`` schema.

        Args:
            keywords: List of keywords to cluster.
            api_key: OpenAI API key.
            embedding_model: OpenAI embedding model name.
            method: Clustering algorithm - kmeans/agglomerative/dbscan/spectral.
            min_keywords_per_cluster: Min keywords per cluster.
            max_keywords_per_cluster: Max keywords per cluster.

        Returns:
            Dict with keywords, labels, cluster_names, silhouette_score, num_clusters.
        """
        from seo_bhishma.core.keyword_sorcerer import (
            cluster_keywords_vectors,
            generate_vector_embeddings,
        )
        from seo_bhishma.models.keyword_sorcerer import ClusterMethod

        vectors = generate_vector_embeddings(keywords, api_key, model=embedding_model)
        result = cluster_keywords_vectors(
            keywords,
            vectors,
            method=ClusterMethod(method),
            min_keywords_per_cluster=min_keywords_per_cluster,
            max_keywords_per_cluster=max_keywords_per_cluster,
        )
        return result.model_dump()
