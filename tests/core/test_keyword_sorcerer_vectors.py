"""Tests for vector-based keyword clustering."""

import numpy as np

from seo_bhishma.core.keyword_sorcerer import (
    calculate_optimal_clusters,
    cluster_keywords_vectors,
)
from seo_bhishma.models.keyword_sorcerer import ClusterMethod


def _toy_vectors() -> tuple[list[str], np.ndarray]:
    keywords = [
        "seo audit",
        "seo audit tool",
        "site audit",
        "keyword research",
        "keyword tool",
        "best keyword tools",
    ]
    # Two clear clusters in 4-D space
    vectors = np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.95, 0.05, 0.0, 0.0],
            [0.9, 0.1, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.95, 0.05],
            [0.0, 0.0, 0.9, 0.1],
        ]
    )
    return keywords, vectors


def test_calculate_optimal_clusters_basic():
    assert calculate_optimal_clusters(20, 4, 8) == (2, 5)
    assert calculate_optimal_clusters(2, 4, 8) == (1, 1)


def test_cluster_keywords_vectors_agglomerative_splits_two_groups():
    keywords, vectors = _toy_vectors()
    result = cluster_keywords_vectors(
        keywords,
        vectors,
        method=ClusterMethod.AGGLOMERATIVE,
        min_keywords_per_cluster=2,
        max_keywords_per_cluster=3,
    )
    assert result.num_clusters >= 2
    # Items 0-2 should share a label distinct from items 3-5
    assert result.labels[0] == result.labels[1] == result.labels[2]
    assert result.labels[3] == result.labels[4] == result.labels[5]
    assert result.labels[0] != result.labels[3]


def test_cluster_keywords_vectors_length_mismatch():
    try:
        cluster_keywords_vectors(["a", "b"], np.array([[1.0]]))
    except ValueError as e:
        assert "length" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")


def test_cluster_keywords_vectors_dbscan_handles_singletons():
    keywords, vectors = _toy_vectors()
    result = cluster_keywords_vectors(
        keywords, vectors, method=ClusterMethod.DBSCAN
    )
    # DBSCAN may label some points as -1 (noise); just verify it runs
    assert len(result.labels) == 6
