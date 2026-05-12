from seo_bhishma.models.gsc_probe import (
    SearchAnalyticsFilter,
    SearchAnalyticsResult,
    SearchAnalyticsRow,
    SitemapInfo,
    UrlInspectionResult,
)


def test_search_analytics_filter():
    f = SearchAnalyticsFilter(
        dimension="query", operator="contains", expression="seo"
    )
    assert f.dimension == "query"
    assert f.operator == "contains"


def test_search_analytics_row():
    row = SearchAnalyticsRow(
        keys=["2024-01-01", "seo tools"],
        clicks=100,
        impressions=5000,
        ctr=0.02,
        position=3.5,
    )
    assert row.clicks == 100
    assert len(row.keys) == 2


def test_search_analytics_result():
    result = SearchAnalyticsResult(
        rows=[
            SearchAnalyticsRow(keys=["2024-01-01"], clicks=10, impressions=100),
        ],
        dimensions=["date"],
        total_rows=1,
    )
    assert result.total_rows == 1


def test_sitemap_info():
    info = SitemapInfo(path="/sitemap.xml", last_downloaded="2024-01-01", sitemap_type="sitemap")
    assert info.path == "/sitemap.xml"


def test_url_inspection_result():
    result = UrlInspectionResult(
        url="https://example.com/page",
        inspection_data={"verdict": "PASS"},
    )
    assert result.inspection_data["verdict"] == "PASS"
