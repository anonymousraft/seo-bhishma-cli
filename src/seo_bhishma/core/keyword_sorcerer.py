"""Core keyword clustering logic using OpenAI embeddings and scikit-learn. No CLI dependencies."""

import logging

import numpy as np
from sklearn.cluster import (
    DBSCAN,
    AgglomerativeClustering,
    KMeans,
    SpectralClustering,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_distances

from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.keyword_sorcerer import ClusterMethod, ClusterResult

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def estimate_token_usage(keywords: list[str]) -> int:
    """Estimate OpenAI API token usage for embedding generation.

    Args:
        keywords: List of keywords to generate embeddings for.

    Returns:
        Estimated total tokens.
    """
    fixed_prompt_tokens = 11
    avg_keyword_tokens = 5
    response_tokens = 50
    tokens_per_keyword = fixed_prompt_tokens + avg_keyword_tokens + response_tokens
    return len(keywords) * tokens_per_keyword


def generate_embeddings(
    keywords: list[str],
    api_key: str,
    model: str = "gpt-4o",
    rate_limit: float = 0.5,
    on_progress: ProgressCallback | None = None,
) -> list[str]:
    """Generate descriptive sentence embeddings for keywords using OpenAI.

    Args:
        keywords: List of keywords to process.
        api_key: OpenAI API key.
        model: OpenAI model name.
        rate_limit: Delay between API calls in seconds.
        on_progress: Optional progress callback.

    Returns:
        List of descriptive sentences (one per keyword).
    """
    import time

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    embeddings: list[str] = []

    for i, keyword in enumerate(keywords):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {
                        "role": "user",
                        "content": (
                            "Generate a descriptive sentence that captures "
                            f"the intent for the keyword: {keyword}"
                        ),
                    },
                ],
                max_tokens=50,
            )
            embedding = response.choices[0].message.content.strip()
            embeddings.append(embedding)
        except Exception as e:
            logger.error("Error generating embedding for '%s': %s", keyword, e)
            embeddings.append("")

        if on_progress:
            on_progress(i + 1, len(keywords))

        if rate_limit > 0:
            time.sleep(rate_limit)

    return embeddings


def generate_vector_embeddings(
    keywords: list[str],
    api_key: str,
    model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 100,
    on_progress: ProgressCallback | None = None,
) -> np.ndarray:
    """Generate real vector embeddings for keywords via OpenAI embeddings API.

    Args:
        keywords: List of keywords.
        api_key: OpenAI API key.
        model: Embedding model name (e.g. "text-embedding-3-small").
        batch_size: How many keywords to embed per API call (max 2048).
        on_progress: Optional progress callback.

    Returns:
        2D ``np.ndarray`` of shape ``(len(keywords), embedding_dim)``.
    """
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    vectors: list[list[float]] = []

    for i in range(0, len(keywords), batch_size):
        batch = keywords[i : i + batch_size]
        try:
            response = client.embeddings.create(model=model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        except Exception as e:
            logger.error("Embedding batch %d-%d failed: %s", i, i + len(batch), e)
            dim = len(vectors[0]) if vectors else 1536
            vectors.extend([0.0] * dim for _ in batch)
        if on_progress:
            on_progress(min(i + batch_size, len(keywords)), len(keywords))

    return np.array(vectors)


def calculate_optimal_clusters(
    n_keywords: int,
    min_keywords_per_cluster: int = 4,
    max_keywords_per_cluster: int = 8,
) -> tuple[int, int]:
    """Calculate optimal cluster count range based on keyword count.

    Args:
        n_keywords: Total number of keywords.
        min_keywords_per_cluster: Minimum keywords per cluster.
        max_keywords_per_cluster: Maximum keywords per cluster.

    Returns:
        Tuple of (min_clusters, max_clusters).
    """
    min_clusters = max(1, n_keywords // max_keywords_per_cluster)
    max_clusters = max(1, n_keywords // min_keywords_per_cluster)
    return min_clusters, max_clusters


def _determine_cluster_names(keywords: list[str], labels: list[int]) -> dict[int, str]:
    """Determine representative name for each cluster."""
    clusters: dict[int, str] = {}
    for label in set(labels):
        cluster_keywords = [kw for kw, lbl in zip(keywords, labels) if lbl == label]
        cluster_name = max(set(cluster_keywords), key=cluster_keywords.count)
        clusters[label] = cluster_name
    return clusters


def _cluster_kmeans(
    embeddings: list[str], min_clusters: int, max_clusters: int
) -> tuple[list[int], float | None]:
    """Cluster using KMeans with optimal cluster selection."""
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    best_score = -1.0
    best_labels = None
    for n_clusters in range(min_clusters, max_clusters + 1):
        model = KMeans(n_clusters=n_clusters, random_state=42)
        labels = model.fit_predict(X)
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_labels = labels
    return best_labels.tolist(), best_score


def _cluster_agglomerative(
    embeddings: list[str], min_clusters: int, max_clusters: int
) -> tuple[list[int], float | None]:
    """Cluster using Agglomerative Clustering."""
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    best_score = -1.0
    best_labels = None
    for n_clusters in range(min_clusters, max_clusters + 1):
        model = AgglomerativeClustering(n_clusters=n_clusters)
        labels = model.fit_predict(X.toarray())
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_labels = labels
    return best_labels.tolist(), best_score


def _cluster_dbscan(embeddings: list[str]) -> tuple[list[int], float | None]:
    """Cluster using DBSCAN."""
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    model = DBSCAN(eps=0.5, min_samples=5)
    labels = model.fit_predict(X)
    try:
        score = silhouette_score(X, labels)
    except ValueError:
        score = None
    return labels.tolist(), score


def _cluster_spectral(
    embeddings: list[str], min_clusters: int, max_clusters: int
) -> tuple[list[int], float | None]:
    """Cluster using Spectral Clustering."""
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(embeddings)
    best_score = -1.0
    best_labels = None
    for n_clusters in range(min_clusters, max_clusters + 1):
        model = SpectralClustering(
            n_clusters=n_clusters, affinity="nearest_neighbors", random_state=42
        )
        labels = model.fit_predict(X)
        score = silhouette_score(X, labels)
        if score > best_score:
            best_score = score
            best_labels = labels
    return best_labels.tolist(), best_score


def cluster_keywords_vectors(
    keywords: list[str],
    vectors: np.ndarray,
    method: ClusterMethod = ClusterMethod.KMEANS,
    min_keywords_per_cluster: int = 4,
    max_keywords_per_cluster: int = 8,
    dbscan_eps: float = 0.3,
    dbscan_min_samples: int = 2,
) -> ClusterResult:
    """Cluster keywords using real embedding vectors with cosine distance.

    Preferred over ``cluster_keywords`` which clusters on TF-IDF of synthetic
    descriptive sentences. Uses precomputed cosine distance for DBSCAN and
    Agglomerative; reduces vectors for KMeans/Spectral.
    """
    if len(keywords) != len(vectors):
        raise ValueError("keywords and vectors length mismatch")

    min_clusters, max_clusters = calculate_optimal_clusters(
        len(keywords), min_keywords_per_cluster, max_keywords_per_cluster
    )

    best_labels: list[int] | None = None
    best_score: float | None = None

    if method == ClusterMethod.KMEANS:
        for n_clusters in range(min_clusters, max_clusters + 1):
            if n_clusters >= len(keywords):
                continue
            model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = model.fit_predict(vectors)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(vectors, labels, metric="cosine")
            if best_score is None or score > best_score:
                best_score = score
                best_labels = labels.tolist()
    elif method == ClusterMethod.AGGLOMERATIVE:
        distances = cosine_distances(vectors)
        for n_clusters in range(min_clusters, max_clusters + 1):
            if n_clusters >= len(keywords):
                continue
            model = AgglomerativeClustering(
                n_clusters=n_clusters, metric="precomputed", linkage="average"
            )
            labels = model.fit_predict(distances)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(distances, labels, metric="precomputed")
            if best_score is None or score > best_score:
                best_score = score
                best_labels = labels.tolist()
    elif method == ClusterMethod.DBSCAN:
        distances = cosine_distances(vectors)
        model = DBSCAN(eps=dbscan_eps, min_samples=dbscan_min_samples, metric="precomputed")
        labels = model.fit_predict(distances)
        best_labels = labels.tolist()
        unique = set(labels) - {-1}
        if len(unique) >= 2:
            try:
                best_score = silhouette_score(distances, labels, metric="precomputed")
            except ValueError:
                best_score = None
    elif method == ClusterMethod.SPECTRAL:
        for n_clusters in range(min_clusters, max_clusters + 1):
            if n_clusters >= len(keywords):
                continue
            model = SpectralClustering(
                n_clusters=n_clusters,
                affinity="nearest_neighbors",
                random_state=42,
                assign_labels="discretize",
            )
            labels = model.fit_predict(vectors)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(vectors, labels, metric="cosine")
            if best_score is None or score > best_score:
                best_score = score
                best_labels = labels.tolist()
    else:
        raise ValueError(f"Unknown clustering method: {method}")

    if best_labels is None:
        # Single cluster fallback
        best_labels = [0] * len(keywords)

    cluster_names = _determine_cluster_names(keywords, best_labels)
    return ClusterResult(
        keywords=keywords,
        labels=best_labels,
        cluster_names=cluster_names,
        silhouette_score=best_score,
        num_clusters=len(set(best_labels)),
    )


def cluster_keywords(
    keywords: list[str],
    embeddings: list[str],
    method: ClusterMethod = ClusterMethod.KMEANS,
    min_keywords_per_cluster: int = 4,
    max_keywords_per_cluster: int = 8,
) -> ClusterResult:
    """Cluster keywords using the specified algorithm.

    Args:
        keywords: Original keywords list.
        embeddings: Descriptive sentences generated from keywords.
        method: Clustering algorithm to use.
        min_keywords_per_cluster: Min keywords per cluster (ignored for DBSCAN).
        max_keywords_per_cluster: Max keywords per cluster (ignored for DBSCAN).

    Returns:
        ClusterResult with labels, cluster names, and score.
    """
    min_clusters, max_clusters = calculate_optimal_clusters(
        len(keywords), min_keywords_per_cluster, max_keywords_per_cluster
    )

    if method == ClusterMethod.KMEANS:
        labels, score = _cluster_kmeans(embeddings, min_clusters, max_clusters)
    elif method == ClusterMethod.AGGLOMERATIVE:
        labels, score = _cluster_agglomerative(embeddings, min_clusters, max_clusters)
    elif method == ClusterMethod.DBSCAN:
        labels, score = _cluster_dbscan(embeddings)
    elif method == ClusterMethod.SPECTRAL:
        labels, score = _cluster_spectral(embeddings, min_clusters, max_clusters)
    else:
        raise ValueError(f"Unknown clustering method: {method}")

    cluster_names = _determine_cluster_names(keywords, labels)

    return ClusterResult(
        keywords=keywords,
        labels=labels,
        cluster_names=cluster_names,
        silhouette_score=score,
        num_clusters=len(set(labels)),
    )
