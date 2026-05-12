from seo_bhishma.models.hannibal import (
    CannibalizationConfig,
    CannibalizationEntry,
    CannibalizationReport,
)


def test_cannibalization_config_defaults():
    config = CannibalizationConfig()
    assert config.exact_match_threshold == 0.2
    assert config.use_semantic_check is False
    assert config.embedding_batch_size == 64


def test_cannibalization_entry():
    entry = CannibalizationEntry(
        primary_url="https://example.com/page-a",
        competing_url="https://example.com/page-b",
        action="Merge into Primary URL",
        query_share_pct=45.0,
        click_share_pct=30.0,
        impression_share_pct=80.0,
        primary_clicks=500,
        primary_impressions=10000,
        primary_ctr=0.05,
        primary_position=3.2,
        competing_clicks=200.0,
        competing_impressions=8000.0,
        competing_ctr=0.025,
        competing_position=5.1,
    )
    assert entry.action == "Merge into Primary URL"
    assert entry.primary_clicks == 500


def test_cannibalization_report():
    report = CannibalizationReport(
        entries=[
            CannibalizationEntry(
                primary_url="https://example.com/a",
                action="Keep as Primary URL",
            )
        ],
        total_clusters=5,
        total_pages_analyzed=20,
    )
    assert report.total_clusters == 5
    assert len(report.entries) == 1
