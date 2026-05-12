"""Core Google Search Console data extraction logic. No CLI dependencies."""

import logging
import time
from datetime import date, datetime, timedelta

from seo_bhishma.core._exceptions import AuthError, NetworkError
from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.gsc_probe import (
    SearchAnalyticsFilter,
    SearchAnalyticsResult,
    SearchAnalyticsRow,
    SitemapInfo,
    UrlInspectionResult,
)

logger = logging.getLogger(__name__)

# Re-exported for convenience; the canonical list lives in agents.google_auth.
SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/webmasters",
]


def authenticate_gsc(
    credentials_path: str | None = None,
    token_path: str | None = None,  # noqa: ARG001  - kept for backward compat
):
    """Authenticate with Google Search Console and return a service object.

    This function no longer runs the interactive OAuth flow inline. The user
    completes login once via ``seo-bhishma gsc login``; we then read the
    saved JSON token (auto-refreshing if expired) on every call. Use the
    Click command if you need to (re-)authorize a machine.

    Args:
        credentials_path: Backward-compat shim — ignored. The CLI now reads
            an override from ``Settings.gsc_credentials_path`` (set via the
            wizard or env var) and the bundled OAuth client from the package.
        token_path: Backward-compat shim — ignored. Tokens are stored under
            the user config directory by :mod:`seo_bhishma.agents.google_auth`.

    Returns:
        An authenticated Search Console API service object.

    Raises:
        AuthError: If no token is available (user hasn't run ``gsc login``)
            or refresh fails irrecoverably.
    """
    from googleapiclient.discovery import build

    from seo_bhishma.agents.google_auth import load_saved_credentials

    creds = load_saved_credentials()
    if creds is None:
        raise AuthError(
            "No saved Google Search Console authentication. "
            "Run `seo-bhishma gsc login` to authorize once."
        )
    if not creds.valid:
        raise AuthError(
            "Saved GSC token is invalid or expired beyond refresh. "
            "Run `seo-bhishma gsc login` again."
        )

    return build("searchconsole", "v1", credentials=creds)


def list_sites(service) -> list[dict]:
    """List all sites available in the GSC account.

    Args:
        service: Authenticated GSC API service.

    Returns:
        List of site entry dicts with 'siteUrl' and 'permissionLevel'.
    """
    try:
        site_list = service.sites().list().execute()
        return site_list.get("siteEntry", [])
    except Exception as e:
        logger.error("Error fetching site list: %s", e)
        return []


PAGE_SIZE = 25000


def fetch_search_analytics(
    service,
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    row_limit: int | None = 25000,
    search_type: str = "web",
    filters: list[SearchAnalyticsFilter] | None = None,
    filter_group_operator: str = "and",
    rate_limit: float = 1.0,
    start_row: int = 0,
    on_progress: ProgressCallback | None = None,
) -> SearchAnalyticsResult:
    """Fetch search analytics data from GSC.

    Paginates through GSC's 25k-rows-per-page cap until ``row_limit`` is
    reached or no more rows are returned.

    Args:
        service: Authenticated GSC API service.
        site_url: Site URL as registered in GSC.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        dimensions: Dimensions to group by (e.g., ["date", "query", "page"]).
        row_limit: Maximum rows to fetch (None for unlimited).
        search_type: Search type (web, image, video, news).
        filters: Optional dimension filters.
        filter_group_operator: ``"and"`` (default) or ``"or"`` between filters.
        rate_limit: Delay between paginated API calls.
        start_row: Resume from this row offset (for checkpoint/resume).
        on_progress: Optional progress callback.

    Returns:
        SearchAnalyticsResult with all fetched rows.

    Raises:
        NetworkError: If the GSC API repeatedly fails.
    """
    if dimensions is None:
        dimensions = ["date"]

    request_body: dict = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": PAGE_SIZE,
        "searchType": search_type,
        "startRow": start_row,
    }

    if filters:
        request_body["dimensionFilterGroups"] = [
            {
                "groupType": filter_group_operator,
                "filters": [f.model_dump() for f in filters],
            }
        ]

    all_rows: list[SearchAnalyticsRow] = []
    total_fetched = start_row
    last_error: Exception | None = None

    while True:
        try:
            response = (
                service.searchanalytics()
                .query(siteUrl=site_url, body=request_body)
                .execute()
            )
            rows = response.get("rows", [])
            if not rows:
                break

            for row in rows:
                all_rows.append(
                    SearchAnalyticsRow(
                        keys=row.get("keys", []),
                        clicks=row.get("clicks", 0),
                        impressions=row.get("impressions", 0),
                        ctr=row.get("ctr", 0),
                        position=row.get("position", 0),
                    )
                )

            total_fetched += len(rows)
            request_body["startRow"] = total_fetched

            if on_progress:
                on_progress(total_fetched, row_limit or total_fetched)

            if row_limit and total_fetched >= row_limit:
                break
            if len(rows) < PAGE_SIZE:
                break

            time.sleep(rate_limit)

        except Exception as e:
            last_error = e
            logger.error("Error fetching search analytics: %s", e)
            break

    if not all_rows and last_error is not None:
        raise NetworkError(f"GSC search analytics request failed: {last_error}") from last_error

    return SearchAnalyticsResult(
        rows=all_rows,
        dimensions=dimensions,
        total_rows=len(all_rows),
    )


def fetch_search_analytics_chunked(
    service,
    site_url: str,
    start_date: str,
    end_date: str,
    chunk_days: int = 30,
    dimensions: list[str] | None = None,
    search_type: str = "web",
    filters: list[SearchAnalyticsFilter] | None = None,
    rate_limit: float = 1.0,
    on_progress: ProgressCallback | None = None,
) -> SearchAnalyticsResult:
    """Fetch GSC analytics in date chunks to avoid hitting per-query row caps.

    Useful when the query dimension is ``query`` or ``page`` and the full
    period would return more than 25k rows.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if start > end:
        raise ValueError("start_date must be <= end_date")

    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    all_rows: list[SearchAnalyticsRow] = []
    for i, (s, e) in enumerate(chunks):
        result = fetch_search_analytics(
            service,
            site_url,
            s.isoformat(),
            e.isoformat(),
            dimensions=dimensions,
            row_limit=None,
            search_type=search_type,
            filters=filters,
            rate_limit=rate_limit,
        )
        all_rows.extend(result.rows)
        if on_progress:
            on_progress(i + 1, len(chunks))

    return SearchAnalyticsResult(
        rows=all_rows,
        dimensions=dimensions or ["date"],
        total_rows=len(all_rows),
    )


def fetch_sitemaps(service, site_url: str) -> list[SitemapInfo]:
    """Fetch sitemap information from GSC.

    Args:
        service: Authenticated GSC API service.
        site_url: Site URL as registered in GSC.

    Returns:
        List of SitemapInfo objects.
    """
    try:
        response = service.sitemaps().list(siteUrl=site_url).execute()
        sitemaps = response.get("sitemap", [])
        return [
            SitemapInfo(
                path=s["path"],
                last_downloaded=s.get("lastDownloaded", ""),
                sitemap_type=s.get("type", ""),
            )
            for s in sitemaps
        ]
    except Exception as e:
        logger.error("Error fetching sitemaps: %s", e)
        return []


def fetch_url_inspection(
    service,
    site_url: str,
    urls: list[str],
    rate_limit: float = 1.0,
    on_progress: ProgressCallback | None = None,
) -> list[UrlInspectionResult]:
    """Inspect URLs using the GSC URL Inspection API.

    Args:
        service: Authenticated GSC API service.
        site_url: Site URL as registered in GSC.
        urls: List of URLs to inspect.
        rate_limit: Delay between API calls.
        on_progress: Optional progress callback.

    Returns:
        List of UrlInspectionResult objects.
    """
    results: list[UrlInspectionResult] = []

    for i, url in enumerate(urls):
        try:
            inspection = (
                service.urlInspection()
                .index()
                .inspect(body={"inspectionUrl": url, "siteUrl": site_url})
                .execute()
            )
            results.append(
                UrlInspectionResult(url=url, inspection_data=inspection)
            )
        except Exception as e:
            logger.error("Error inspecting URL %s: %s", url, e)
            results.append(
                UrlInspectionResult(url=url, inspection_data={"error": str(e)})
            )

        if on_progress:
            on_progress(i + 1, len(urls))

        time.sleep(rate_limit)

    return results


def get_available_dates(service, site_url: str) -> tuple[str | None, str | None]:
    """Get the earliest and latest available dates for a site in GSC.

    Args:
        service: Authenticated GSC API service.
        site_url: Site URL as registered in GSC.

    Returns:
        Tuple of (start_date, end_date) as strings, or (None, None) on failure.
    """
    try:
        response = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": "2000-01-01",
                    "endDate": "2100-01-01",
                    "dimensions": ["date"],
                    "rowLimit": 1,
                },
            )
            .execute()
        )
        if "rows" in response:
            start_date = response["rows"][0]["keys"][0]
            end_date = response["rows"][-1]["keys"][0]
            return start_date, end_date
    except Exception as e:
        logger.error("Error fetching available dates: %s", e)

    return None, None
