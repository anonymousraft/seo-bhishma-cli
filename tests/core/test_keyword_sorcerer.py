from seo_bhishma.models.keyword_sorcerer import ClusterMethod, ClusterResult


def test_cluster_method_enum():
    assert ClusterMethod.KMEANS == "kmeans"
    assert ClusterMethod.AGGLOMERATIVE == "agglomerative"
    assert ClusterMethod.DBSCAN == "dbscan"
    assert ClusterMethod.SPECTRAL == "spectral"


def test_cluster_result_model():
    result = ClusterResult(
        keywords=["seo tools", "keyword research", "backlink checker"],
        labels=[0, 0, 1],
        cluster_names={0: "seo tools", 1: "backlink checker"},
        silhouette_score=0.75,
        num_clusters=2,
    )
    assert result.num_clusters == 2
    assert len(result.keywords) == 3
    assert result.silhouette_score == 0.75


def test_cluster_result_optional_score():
    result = ClusterResult(
        keywords=["a", "b"],
        labels=[0, 1],
        cluster_names={0: "a", 1: "b"},
        num_clusters=2,
    )
    assert result.silhouette_score is None
