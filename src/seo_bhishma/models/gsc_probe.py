"""Models for Google Search Console data extraction (GSC Probe)."""

from pydantic import BaseModel


class SearchAnalyticsFilter(BaseModel):
    """A single dimension filter for GSC search analytics."""

    dimension: str
    operator: str = "equals"
    expression: str


class SearchAnalyticsRequest(BaseModel):
    """Parameters for a GSC search analytics query."""

    site_url: str
    start_date: str
    end_date: str
    dimensions: list[str] = ["date"]
    row_limit: int | None = 25000
    search_type: str = "web"
    filters: list[SearchAnalyticsFilter] = []


class SearchAnalyticsRow(BaseModel):
    """A single row from GSC search analytics response."""

    keys: list[str] = []
    clicks: float = 0
    impressions: float = 0
    ctr: float = 0
    position: float = 0


class SearchAnalyticsResult(BaseModel):
    """Result of a search analytics query."""

    rows: list[SearchAnalyticsRow]
    dimensions: list[str]
    total_rows: int


class SitemapInfo(BaseModel):
    """Information about a sitemap from GSC."""

    path: str
    last_downloaded: str = ""
    sitemap_type: str = ""


class UrlInspectionResult(BaseModel):
    """Result of a URL inspection from GSC."""

    url: str
    inspection_data: dict
