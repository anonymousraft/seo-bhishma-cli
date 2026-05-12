"""Models for URL cannibalization detection (Hannibal)."""

from pydantic import BaseModel


class CannibalizationConfig(BaseModel):
    """Configuration for cannibalization detection."""

    exact_match_threshold: float = 0.2
    impression_share_threshold: float = 0.7
    click_share_threshold: float = 0.2
    query_share_threshold: float = 25.0
    use_slug_similarity: bool = False
    slug_similarity_threshold: float = 0.5
    use_semantic_check: bool = False
    # AgglomerativeClustering distance_threshold on PCA-reduced embeddings;
    # higher = fewer/larger clusters. Not a cosine similarity.
    semantic_match_threshold: float = 1.5
    embedding_batch_size: int = 64
    pca_components: int = 100


class CannibalizationEntry(BaseModel):
    """A single entry in the cannibalization report."""

    primary_url: str
    competing_url: str = "NA"
    exact_match_queries: str = "NA"
    query_share_pct: float | str = "NA"
    click_share_pct: float | str = "NA"
    impression_share_pct: float | str = "NA"
    action: str = "Keep as Primary URL"
    primary_clicks: float = 0
    primary_impressions: float = 0
    primary_ctr: float = 0
    primary_position: float = 0
    competing_clicks: float | str = "NA"
    competing_impressions: float | str = "NA"
    competing_ctr: float | str = "NA"
    competing_position: float | str = "NA"


class CannibalizationReport(BaseModel):
    """Full cannibalization analysis report."""

    entries: list[CannibalizationEntry]
    total_clusters: int
    total_pages_analyzed: int
