"""Models for keyword clustering (Keyword Sorcerer)."""

from enum import Enum

from pydantic import BaseModel


class ClusterMethod(str, Enum):
    """Supported clustering algorithms."""

    KMEANS = "kmeans"
    AGGLOMERATIVE = "agglomerative"
    DBSCAN = "dbscan"
    SPECTRAL = "spectral"


class ClusterResult(BaseModel):
    """Result of keyword clustering."""

    keywords: list[str]
    labels: list[int]
    cluster_names: dict[int, str]
    silhouette_score: float | None = None
    num_clusters: int
