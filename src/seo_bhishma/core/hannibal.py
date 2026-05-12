"""Core URL cannibalization detection logic. No CLI dependencies."""

import logging
from difflib import SequenceMatcher

import numpy as np
import pandas as pd

from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.hannibal import (
    CannibalizationConfig,
    CannibalizationEntry,
    CannibalizationReport,
)

logger = logging.getLogger(__name__)


def load_gsc_data(file_path: str) -> pd.DataFrame:
    """Load GSC data from a CSV file and normalize column names.

    Tries UTF-8 first, then falls back to ``utf-8-sig`` and ``cp1252`` for
    Excel-exported CSVs. Strips thousands separators and percent signs.

    Args:
        file_path: Path to the CSV file.

    Returns:
        DataFrame with normalized columns.

    Raises:
        ValueError: If required columns are missing.
    """
    df: pd.DataFrame | None = None
    last_exc: Exception | None = None
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(file_path, encoding=enc)
            break
        except UnicodeDecodeError as e:
            last_exc = e
            continue
    if df is None:
        raise ValueError(f"Unable to read CSV with common encodings: {last_exc}")

    df.columns = df.columns.str.strip().str.lower()

    required = {"page", "query", "clicks", "impressions", "ctr", "position"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Normalize numeric columns
    df["clicks"] = df["clicks"].astype(str).str.replace(",", "").astype(float)
    df["impressions"] = df["impressions"].astype(str).str.replace(",", "").astype(float)
    df["ctr"] = df["ctr"].astype(str).str.replace("%", "").astype(float) / 100
    df["position"] = df["position"].astype(float)

    return df


def aggregate_data(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate GSC data by page, collecting queries per page.

    Args:
        df: Raw GSC DataFrame with page, query, clicks, impressions, ctr, position.

    Returns:
        Aggregated DataFrame grouped by page.
    """
    return (
        df.groupby("page")
        .agg(
            {
                "query": lambda x: list(x),
                "clicks": "sum",
                "impressions": "sum",
                "ctr": "mean",
                "position": "mean",
            }
        )
        .reset_index()
    )


def compute_slug_similarity(slug1: str, slug2: str) -> float:
    """Compute similarity between two URL slugs using SequenceMatcher."""
    return SequenceMatcher(None, slug1, slug2).ratio()


def get_embeddings(
    data: pd.DataFrame,
    batch_size: int = 64,
    on_progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Generate embeddings for queries + URL slugs using sentence-transformers.

    Args:
        data: Aggregated DataFrame with 'query' (list) and 'page' columns.
        batch_size: Batch size for encoding.
        on_progress: Optional progress callback.

    Returns:
        Numpy array of embeddings.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    combined_text = (
        data["query"].apply(lambda x: " ".join(x)).astype(str)
        + " "
        + data["page"].astype(str)
    ).tolist()

    embeddings: list[np.ndarray] = []
    total = len(combined_text)

    for i in range(0, total, batch_size):
        batch = combined_text[i : i + batch_size]
        batch_embeddings = model.encode(batch)
        embeddings.extend(batch_embeddings)
        if on_progress:
            on_progress(min(i + batch_size, total), total)

    return np.array(embeddings)


def reduce_dimensionality(
    embeddings: np.ndarray, n_components: int = 100
) -> np.ndarray:
    """Reduce embedding dimensionality using PCA.

    Args:
        embeddings: High-dimensional embeddings.
        n_components: Target dimensions.

    Returns:
        Reduced embeddings.
    """
    from sklearn.decomposition import PCA

    pca = PCA(n_components=min(n_components, embeddings.shape[1], embeddings.shape[0]))
    return pca.fit_transform(embeddings)


def cluster_urls(
    df: pd.DataFrame,
    embeddings: np.ndarray | None,
    config: CannibalizationConfig,
    on_progress: ProgressCallback | None = None,
) -> list[list[str]]:
    """Cluster URLs based on query overlap, slug similarity, or semantic similarity.

    Args:
        df: Aggregated DataFrame.
        embeddings: Optional embeddings for semantic clustering.
        config: Cannibalization detection configuration.
        on_progress: Optional progress callback.

    Returns:
        List of clusters, where each cluster is a list of page URLs.
    """
    clusters: list[list[str]] = []

    if config.use_semantic_check and embeddings is not None:
        from sklearn.cluster import AgglomerativeClustering

        clustering = AgglomerativeClustering(
            n_clusters=None, distance_threshold=config.semantic_match_threshold
        )
        labels = clustering.fit_predict(embeddings)

        for label in np.unique(labels):
            cluster = df["page"].iloc[np.where(labels == label)[0]].tolist()
            clusters.append(cluster)
    else:
        url_groups = df.groupby("page")
        processed_urls: set[str] = set()
        total = len(url_groups)
        completed = 0

        for primary_url, primary_data in url_groups:
            if primary_url in processed_urls:
                completed += 1
                if on_progress:
                    on_progress(completed, total)
                continue

            cluster = [primary_url]
            processed_urls.add(primary_url)

            for competing_url, competing_data in url_groups:
                if competing_url in processed_urls or competing_url == primary_url:
                    continue

                exact_match_queries = set(primary_data["query"].values[0]).intersection(
                    set(competing_data["query"].values[0])
                )
                exact_match_ratio = len(exact_match_queries) / max(
                    len(primary_data["query"].values[0]), 1
                )

                slug_similarity = 0.0
                if config.use_slug_similarity:
                    slug_similarity = compute_slug_similarity(
                        primary_url, competing_url
                    )

                if (
                    exact_match_ratio >= config.exact_match_threshold
                    or slug_similarity >= config.slug_similarity_threshold
                ):
                    cluster.append(competing_url)
                    processed_urls.add(competing_url)

            clusters.append(cluster)
            completed += 1
            if on_progress:
                on_progress(completed, total)

    return clusters


def select_primary_urls(
    clusters: list[list[str]],
    df: pd.DataFrame,
    config: CannibalizationConfig,
) -> list[CannibalizationEntry]:
    """Select primary URLs within clusters and identify cannibalization.

    Args:
        clusters: List of URL clusters.
        df: Aggregated DataFrame.
        config: Cannibalization configuration with thresholds.

    Returns:
        List of CannibalizationEntry objects.
    """
    entries: list[CannibalizationEntry] = []

    for cluster in clusters:
        if len(cluster) == 1:
            page_data = df[df["page"] == cluster[0]]
            entries.append(
                CannibalizationEntry(
                    primary_url=cluster[0],
                    action="Keep as Primary URL",
                    primary_clicks=float(page_data["clicks"].sum()),
                    primary_impressions=float(page_data["impressions"].sum()),
                    primary_ctr=float(page_data["ctr"].mean()),
                    primary_position=float(page_data["position"].mean()),
                )
            )
            continue

        # Select URL with highest clicks as initial primary
        best_url = max(
            cluster, key=lambda url: df[df["page"] == url]["clicks"].sum()
        )

        has_competing = False
        for url in cluster:
            if url == best_url:
                continue

            primary_data = df[df["page"] == best_url]
            competing_data = df[df["page"] == url]
            exact_match_queries = set(primary_data["query"].values[0]).intersection(
                set(competing_data["query"].values[0])
            )

            matching_primary_clicks = primary_data[
                primary_data["query"].apply(
                    lambda x: any(q in exact_match_queries for q in x)
                )
            ]["clicks"].sum()
            matching_primary_impressions = primary_data[
                primary_data["query"].apply(
                    lambda x: any(q in exact_match_queries for q in x)
                )
            ]["impressions"].sum()

            matching_competing_clicks = competing_data[
                competing_data["query"].apply(
                    lambda x: any(q in exact_match_queries for q in x)
                )
            ]["clicks"].sum()
            matching_competing_impressions = competing_data[
                competing_data["query"].apply(
                    lambda x: any(q in exact_match_queries for q in x)
                )
            ]["impressions"].sum()

            query_share = (
                (len(exact_match_queries) / len(primary_data["query"].values[0])) * 100
                if len(primary_data["query"].values[0]) > 0
                else 0
            )

            if (
                matching_primary_clicks < 0.8 * primary_data["clicks"].sum()
                or matching_primary_impressions
                < 0.8 * primary_data["impressions"].sum()
            ):
                continue

            click_share = (
                (matching_competing_clicks / matching_primary_clicks) * 100
                if matching_primary_clicks > 0
                else 0
            )
            impression_share = (
                (matching_competing_impressions / matching_primary_impressions) * 100
                if matching_primary_impressions > 0
                else 0
            )

            # Swap primary if competing has more clicks and impressions
            if (
                matching_competing_clicks > matching_primary_clicks
                and matching_competing_impressions > matching_primary_impressions
            ):
                best_url = url
                primary_data = df[df["page"] == best_url]

            if query_share < config.query_share_threshold:
                continue

            if (
                impression_share >= config.impression_share_threshold * 100
                or click_share >= config.click_share_threshold * 100
            ):
                has_competing = True
                entries.append(
                    CannibalizationEntry(
                        primary_url=best_url,
                        competing_url=url,
                        exact_match_queries=", ".join(exact_match_queries)
                        if exact_match_queries
                        else "NA",
                        query_share_pct=query_share,
                        click_share_pct=click_share,
                        impression_share_pct=impression_share,
                        action="Merge into Primary URL",
                        primary_clicks=float(primary_data["clicks"].sum()),
                        primary_impressions=float(primary_data["impressions"].sum()),
                        primary_ctr=float(primary_data["ctr"].mean()),
                        primary_position=float(primary_data["position"].mean()),
                        competing_clicks=float(competing_data["clicks"].sum()),
                        competing_impressions=float(
                            competing_data["impressions"].sum()
                        ),
                        competing_ctr=float(competing_data["ctr"].mean()),
                        competing_position=float(competing_data["position"].mean()),
                    )
                )

        if not has_competing:
            page_data = df[df["page"] == best_url]
            entries.append(
                CannibalizationEntry(
                    primary_url=best_url,
                    action="Keep as Primary URL",
                    primary_clicks=float(page_data["clicks"].sum()),
                    primary_impressions=float(page_data["impressions"].sum()),
                    primary_ctr=float(page_data["ctr"].mean()),
                    primary_position=float(page_data["position"].mean()),
                )
            )

    return entries


def detect_cannibalization(
    file_path: str,
    config: CannibalizationConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> CannibalizationReport:
    """Run full cannibalization detection pipeline.

    Args:
        file_path: Path to GSC data CSV.
        config: Detection configuration (uses defaults if None).
        on_progress: Optional progress callback.

    Returns:
        CannibalizationReport with all entries.
    """
    if config is None:
        config = CannibalizationConfig()

    df = load_gsc_data(file_path)
    aggregated = aggregate_data(df)

    embeddings = None
    if config.use_semantic_check:
        embeddings = get_embeddings(
            aggregated, batch_size=config.embedding_batch_size, on_progress=on_progress
        )
        embeddings = reduce_dimensionality(embeddings, n_components=config.pca_components)

    clusters = cluster_urls(aggregated, embeddings, config, on_progress=on_progress)
    entries = select_primary_urls(clusters, aggregated, config)

    return CannibalizationReport(
        entries=entries,
        total_clusters=len(clusters),
        total_pages_analyzed=len(aggregated),
    )
