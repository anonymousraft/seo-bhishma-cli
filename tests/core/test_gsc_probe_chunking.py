"""Tests for GSC fetch chunking and pagination logic."""

from unittest.mock import MagicMock

from seo_bhishma.core.gsc_probe import (
    PAGE_SIZE,
    fetch_search_analytics,
    fetch_search_analytics_chunked,
)


def _make_service(pages: list[list[dict]]):
    """Build a fake GSC service whose searchanalytics().query().execute() returns
    successive pages from ``pages``."""
    service = MagicMock()
    calls = {"i": 0}

    def execute():
        i = calls["i"]
        calls["i"] += 1
        if i < len(pages):
            return {"rows": pages[i]}
        return {"rows": []}

    service.searchanalytics.return_value.query.return_value.execute.side_effect = execute
    return service


def test_fetch_search_analytics_pagination_stops_on_empty():
    rows_page = [{"keys": [f"2025-01-0{i}"], "clicks": i, "impressions": 10 * i} for i in range(1, 4)]
    service = _make_service([rows_page])

    result = fetch_search_analytics(
        service, "https://example.com", "2025-01-01", "2025-01-31",
        row_limit=None, rate_limit=0,
    )
    assert result.total_rows == 3
    assert result.rows[0].clicks == 1


def test_fetch_search_analytics_short_page_terminates():
    # 1 page of < PAGE_SIZE rows means we stop (no further requests)
    page = [{"keys": ["k"], "clicks": 1, "impressions": 2} for _ in range(5)]
    service = _make_service([page])

    result = fetch_search_analytics(
        service, "https://example.com", "2025-01-01", "2025-01-31",
        row_limit=None, rate_limit=0,
    )
    assert result.total_rows == 5
    # Should have called execute exactly once
    assert service.searchanalytics.return_value.query.return_value.execute.call_count == 1


def test_fetch_search_analytics_chunked_splits_dates():
    # 90 days, chunk_days=30 → 3 chunks
    page = [{"keys": ["k"], "clicks": 1}] * 2
    service = _make_service([page, page, page])

    result = fetch_search_analytics_chunked(
        service, "https://example.com", "2025-01-01", "2025-03-31",
        chunk_days=30, rate_limit=0,
    )
    assert result.total_rows == 6


def test_fetch_search_analytics_chunked_validates_dates():
    service = _make_service([])
    try:
        fetch_search_analytics_chunked(
            service, "https://example.com", "2025-12-01", "2025-01-01"
        )
    except ValueError as e:
        assert "start_date" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_page_size_constant():
    assert PAGE_SIZE == 25000
