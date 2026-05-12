"""Core backlink checking logic. No CLI dependencies."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from seo_bhishma.core._http import DEFAULT_TIMEOUT, requests_retry_session
from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.link_sniper import BacklinkCheckRequest, BacklinkCheckResult

logger = logging.getLogger(__name__)

NOFOLLOW_REL_VALUES = {"nofollow", "sponsored", "ugc"}


def _normalize_target(url: str) -> str:
    return url.rstrip("/")


def _rel_attrs(tag) -> list[str]:
    rel = tag.get("rel")
    if not rel:
        return []
    if isinstance(rel, str):
        return [v.strip().lower() for v in rel.split() if v.strip()]
    return [v.strip().lower() for v in rel if v and v.strip()]


def check_backlink(
    backlink_url: str,
    target_url: str,
    expected_anchor: str = "",
) -> BacklinkCheckResult:
    """Check if a backlink is live and verify anchor text and rel attributes.

    Args:
        backlink_url: The URL that should contain the backlink.
        target_url: The URL that should be linked to.
        expected_anchor: Optional anchor text to verify.

    Returns:
        BacklinkCheckResult with status, anchor details, rel attributes, and HTTP status.
    """
    try:
        response = requests_retry_session().get(backlink_url, timeout=DEFAULT_TIMEOUT)
        http_status = response.status_code
        if http_status != 200:
            return BacklinkCheckResult(
                backlink_url=backlink_url,
                target_url=target_url,
                status="Not Live",
                anchor_status="N/A",
                link_exists="No",
                http_status=http_status,
            )

        soup = BeautifulSoup(response.text, "html.parser")
        target_norm = _normalize_target(target_url)
        links = [
            a for a in soup.find_all("a", href=True)
            if _normalize_target(a["href"]) == target_norm
        ]
        if not links:
            return BacklinkCheckResult(
                backlink_url=backlink_url,
                target_url=target_url,
                status="Not Found",
                anchor_status="N/A",
                link_exists="No",
                http_status=http_status,
            )

        actual_anchor_texts = [link.get_text(strip=True) for link in links]
        joined_anchors = ", ".join(actual_anchor_texts)

        rel_values: list[str] = []
        for link in links:
            for v in _rel_attrs(link):
                if v not in rel_values:
                    rel_values.append(v)
        is_dofollow = not any(v in NOFOLLOW_REL_VALUES for v in rel_values)

        anchor_status = "Present"
        if expected_anchor:
            anchor_present = any(expected_anchor in (a or "") for a in actual_anchor_texts)
            anchor_status = "Present" if anchor_present else "Missing"

        return BacklinkCheckResult(
            backlink_url=backlink_url,
            target_url=target_url,
            status="Live",
            anchor_status=anchor_status,
            link_exists="Yes",
            actual_anchor_text=joined_anchors,
            http_status=http_status,
            rel_values=rel_values,
            is_dofollow=is_dofollow,
        )
    except Exception as e:
        logger.error("Error checking backlink %s: %s", backlink_url, e)
        return BacklinkCheckResult(
            backlink_url=backlink_url,
            target_url=target_url,
            status="Error",
            anchor_status=str(e),
            link_exists="No",
        )


def batch_check_backlinks(
    checks: list[BacklinkCheckRequest],
    max_workers: int = 10,
    on_progress: ProgressCallback | None = None,
) -> list[BacklinkCheckResult]:
    """Check multiple backlinks in parallel.

    Args:
        checks: List of backlink check requests.
        max_workers: Max concurrent threads.
        on_progress: Optional callback for progress reporting.

    Returns:
        List of BacklinkCheckResult in the same order as input.
    """
    results: list[BacklinkCheckResult | None] = [None] * len(checks)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                check_backlink,
                check.backlink_url,
                check.target_url,
                check.expected_anchor,
            ): i
            for i, check in enumerate(checks)
        }
        completed = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
            completed += 1
            if on_progress:
                on_progress(completed, len(checks))

    return results  # type: ignore[return-value]


def read_backlinks_from_csv(file_path: str) -> list[BacklinkCheckRequest]:
    """Load backlink check requests from a CSV or JSON file.

    Required columns: ``backlink_url``, ``target_url``. Optional: ``expected_anchor``.
    """
    import pandas as pd

    if file_path.endswith(".json"):
        df = pd.read_json(file_path)
    else:
        df = pd.read_csv(file_path)

    required = {"backlink_url", "target_url"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if "expected_anchor" not in df.columns:
        df["expected_anchor"] = ""
    df["expected_anchor"] = df["expected_anchor"].fillna("").astype(str)

    return [
        BacklinkCheckRequest(
            backlink_url=str(row["backlink_url"]),
            target_url=str(row["target_url"]),
            expected_anchor=str(row["expected_anchor"]),
        )
        for _, row in df.iterrows()
    ]
