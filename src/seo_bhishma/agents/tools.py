"""LangChain ``@tool``-wrapped SEO operations the chat agent can call.

Each tool delegates to a function in :mod:`seo_bhishma.core` and returns a
JSON-serializable summary (string / dict). Long descriptions are intentional —
they drive LLM tool selection accuracy.

Each tool also has an authorization tier set as ``tool.metadata["auth_tier"]``,
consumed by :mod:`seo_bhishma.agents.graph` to decide whether to interrupt for
user confirmation:

* ``"auto"``: read-only, fast — runs without prompting.
* ``"confirm_once"``: cost-/time-sensitive (paid APIs, batch ops, OAuth) —
  prompts once per session, decision is remembered.
* ``"confirm_each"``: writes a file — prompts every time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from langchain_core.tools import tool

from seo_bhishma.config.settings import Settings
from seo_bhishma.core import (
    domain_insight as _domain,
)
from seo_bhishma.core import (
    gsc_probe as _gsc,
)
from seo_bhishma.core import (
    hannibal as _hannibal,
)
from seo_bhishma.core import (
    index_spy as _index_spy,
)
from seo_bhishma.core import (
    keyword_sorcerer as _ks,
)
from seo_bhishma.core import (
    link_sniper as _ls,
)
from seo_bhishma.core import (
    redirection_genius as _rg,
)
from seo_bhishma.core import (
    site_mapper as _sm,
)
from seo_bhishma.core import (
    sitemap_generator as _sg,
)
from seo_bhishma.models.hannibal import CannibalizationConfig
from seo_bhishma.models.index_spy import CheckMethod
from seo_bhishma.models.keyword_sorcerer import ClusterMethod
from seo_bhishma.models.link_sniper import BacklinkCheckRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _gsc_service():
    """Return a cached authenticated GSC service, or raise a clear error."""
    settings = Settings()
    if not settings.gsc_credentials_path:
        raise ValueError(
            "GSC credentials not configured. "
            "Set SEO_BHISHMA_GSC_CREDENTIALS_PATH to your OAuth JSON file."
        )
    return _gsc.authenticate_gsc(
        settings.gsc_credentials_path,
        settings.gsc_token_path or "token.pickle",
    )


# ---------------------------------------------------------------------------
# Read-only tools (auth tier: "auto")
# ---------------------------------------------------------------------------


@tool
def check_backlink(
    backlink_url: str, target_url: str, expected_anchor: str = ""
) -> dict:
    """Check whether a single backlink is live and links to ``target_url``.

    Use this when the user wants to verify ONE specific backlink. Returns
    status (Live / Not Live / Not Found / Error), anchor-text presence,
    rel attributes, and dofollow status.
    """
    result = _ls.check_backlink(backlink_url, target_url, expected_anchor)
    return result.model_dump()


@tool
def get_dns_records(domain: str) -> dict:
    """Look up A / AAAA / MX / NS / TXT / CNAME DNS records for a domain.

    Use for "what are the DNS records for X" or "is MX set up for X".
    """
    return _domain.get_dns_records(domain).model_dump()


@tool
def get_whois_info(domain: str) -> dict:
    """Fetch WHOIS registration data for a domain (registrar, dates, contacts)."""
    return _domain.get_whois_info(domain).model_dump()


@tool
def get_ssl_certificate(domain: str) -> dict:
    """Fetch the live TLS certificate for a domain (issuer, validity dates, SANs).

    Use for "is X's SSL cert expired" or "who issued X's certificate".
    """
    return _domain.get_ssl_certificate(domain).model_dump()


@tool
def get_security_headers(domain: str) -> dict:
    """Fetch HTTP security headers (HSTS, CSP, X-Frame-Options, etc.) and grade A-F."""
    return _domain.get_security_headers(domain).model_dump()


@tool
def fetch_robots_txt(domain: str) -> dict:
    """Fetch and parse robots.txt for a domain. Returns disallow rules + sitemap URLs."""
    result = _domain.fetch_robots_txt(domain)
    if result is None:
        return {"found": False, "message": "robots.txt not found"}
    return {"found": True, **result.model_dump()}


@tool
def tech_stack_analysis(domain: str) -> dict:
    """Detect web technologies on a domain via Wappalyzer (CMS, frameworks, analytics)."""
    return _domain.tech_analysis(domain).model_dump()


@tool
def get_ip_address(domain: str) -> dict:
    """Resolve a domain to its primary IPv4 address."""
    ip = _domain.get_ip_address(domain)
    return {"domain": domain, "ip": ip}


@tool
def get_ip_details(ip: str) -> dict:
    """Fetch ASN, geolocation, and ISP information for an IP address."""
    return _domain.get_ip_details(ip).model_dump()


@tool
def check_indexing_status(url: str, use_playwright: bool = False) -> dict:
    """Check whether a single URL is indexed in Google via ``site:`` query.

    Args:
        url: The URL to check.
        use_playwright: If True, use a real browser (slower, more accurate when
            HTMLSession is blocked). Default False uses HTMLSession.
    """
    method = CheckMethod.PLAYWRIGHT if use_playwright else CheckMethod.HTML_SESSION
    result = _index_spy.check_indexing_status(url, method=method, headless=True)
    return result.model_dump()


@tool
def discover_sitemaps(domain: str) -> dict:
    """Discover sitemap URLs declared in a domain's robots.txt (with fallbacks).

    Returns the ordered list of sitemap URLs found, or the fallback
    ``https://<domain>/sitemap.xml`` if none declared.
    """
    sitemaps = _sm.discover_sitemaps_from_robots(domain)
    return {"domain": domain, "sitemaps": sitemaps}


@tool
def parse_sitemap(sitemap_url: str) -> dict:
    """Download and parse a sitemap (including nested + gzipped). Returns URL count + sample.

    For large sitemaps, only the first 50 URLs are inlined in the result;
    the rest are summarized as counts.
    """
    result = _sm.download_and_parse_sitemap(sitemap_url)
    if result is None:
        return {"success": False, "message": f"Failed to download {sitemap_url}"}
    sample = [u.loc for u in result.urls[:50]]
    return {
        "success": True,
        "sitemaps_parsed": result.total_sitemaps_parsed,
        "total_urls": len(result.urls),
        "sample_urls": sample,
        "note": (
            f"Sample shows first 50 of {len(result.urls)} URLs."
            if len(result.urls) > 50
            else None
        ),
    }


@tool
def gsc_list_sites() -> dict:
    """List sites available in the user's Google Search Console account.

    Requires ``SEO_BHISHMA_GSC_CREDENTIALS_PATH`` and may trigger an OAuth
    browser flow on first use.
    """
    service = _gsc_service()
    sites = _gsc.list_sites(service)
    return {"sites": [s.get("siteUrl") for s in sites], "count": len(sites)}


# ---------------------------------------------------------------------------
# Cost/time-sensitive tools (auth tier: "confirm_once")
# ---------------------------------------------------------------------------


@tool
def batch_check_backlinks(input_csv: str, output_csv: str = "") -> dict:
    """Check many backlinks at once from a CSV (columns: backlink_url, target_url, expected_anchor).

    Returns counts and the saved CSV path. Output defaults to a timestamped
    file in the current directory.
    """
    checks = _ls.read_backlinks_from_csv(input_csv)
    results = _ls.batch_check_backlinks(checks)
    output_csv = output_csv or f"backlinks_{_timestamp()}.csv"
    pd.DataFrame([r.model_dump() for r in results]).to_csv(
        output_csv, index=False, encoding="utf-8"
    )
    live = sum(1 for r in results if r.status == "Live")
    return {
        "checked": len(results),
        "live": live,
        "not_live": sum(1 for r in results if r.status == "Not Live"),
        "not_found": sum(1 for r in results if r.status == "Not Found"),
        "errors": sum(1 for r in results if r.status == "Error"),
        "output_csv": output_csv,
    }


@tool
def batch_check_indexing(
    input_csv: str,
    output_csv: str = "",
    use_playwright: bool = False,
    rate_limit: float = 0,
) -> dict:
    """Check Google indexing status for many URLs (input CSV must contain a 'url' column).

    Output defaults to a timestamped CSV. ``rate_limit`` is seconds of delay
    between requests; recommended >=1 if not using a proxy.
    """
    if input_csv.endswith(".json"):
        df = pd.read_json(input_csv)
    else:
        df = pd.read_csv(input_csv)
    if "url" not in df.columns:
        raise ValueError("Input file must contain a 'url' column.")
    urls = df["url"].dropna().astype(str).tolist()

    method = CheckMethod.PLAYWRIGHT if use_playwright else CheckMethod.HTML_SESSION
    batch = _index_spy.batch_check_indexing(
        urls, method=method, rate_limit=rate_limit, headless=True
    )
    output_csv = output_csv or f"indexing_{_timestamp()}.csv"
    pd.DataFrame([r.model_dump() for r in batch.results]).to_csv(
        output_csv, index=False, encoding="utf-8"
    )
    return {
        "checked": batch.total_checked,
        "indexed": batch.total_indexed,
        "not_indexed": batch.total_not_indexed,
        "errors": batch.total_errors,
        "output_csv": output_csv,
    }


@tool
def gsc_fetch_search_analytics(
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: list[str] | None = None,
    row_limit: int = 25000,
    search_type: str = "web",
    output_csv: str = "",
) -> dict:
    """Fetch Search Console analytics for a site over a date range.

    Args:
        site_url: Site as listed in GSC (e.g. ``"sc-domain:example.com"``).
        start_date: YYYY-MM-DD.
        end_date: YYYY-MM-DD.
        dimensions: e.g. ``["date"]``, ``["page"]``, ``["query"]``. Default ``["date"]``.
        row_limit: Max rows. Use a small number (10-100) for "top X" queries.
        search_type: ``"web"`` | ``"image"`` | ``"video"`` | ``"news"``.
        output_csv: Optional output path. If omitted, a timestamped file is used.

    Returns counts and the output CSV path (truncated head shown to the agent).
    """
    service = _gsc_service()
    result = _gsc.fetch_search_analytics(
        service,
        site_url,
        start_date,
        end_date,
        dimensions=dimensions or ["date"],
        row_limit=row_limit,
        search_type=search_type,
    )
    flat: list[dict] = []
    dims = result.dimensions
    for r in result.rows:
        row: dict = {}
        for dim, key in zip(dims, r.keys):
            row[dim] = key
        row.update(clicks=r.clicks, impressions=r.impressions, ctr=r.ctr, position=r.position)
        flat.append(row)
    output_csv = output_csv or f"gsc_{_timestamp()}.csv"
    if flat:
        pd.DataFrame(flat).to_csv(output_csv, index=False, encoding="utf-8")
    return {
        "rows": len(flat),
        "output_csv": output_csv if flat else None,
        "head": flat[:10],
    }


@tool
def gsc_fetch_sitemaps(site_url: str) -> dict:
    """List sitemaps registered in Search Console for a site."""
    service = _gsc_service()
    sitemaps = _gsc.fetch_sitemaps(service, site_url)
    return {"count": len(sitemaps), "sitemaps": [s.model_dump() for s in sitemaps]}


@tool
def find_subdomains(domain: str) -> dict:
    """Enumerate subdomains via sublist3r (uses search engines; can be slow)."""
    subs = _domain.find_subdomains(domain)
    return {"domain": domain, "count": len(subs), "subdomains": list(subs)}


@tool
def map_redirect_urls(
    input_csv: str,
    output_csv: str = "",
    use_web_content: bool = False,
    rate_limit: float = 0,
) -> dict:
    """Build a source→destination redirect map from a CSV (columns: source, destination).

    Uses TF-IDF + spaCy on URL slugs; ``use_web_content=True`` adds a content
    comparison for low-confidence matches (slower, makes HTTP requests).
    """
    df = pd.read_csv(input_csv)
    if "source" not in df.columns or "destination" not in df.columns:
        raise ValueError("Input CSV must contain 'source' and 'destination' columns.")
    sources = df["source"].dropna().astype(str).tolist()
    dests = df["destination"].dropna().astype(str).tolist()
    results = _rg.map_urls(sources, dests, use_web_content=use_web_content, rate_limit=rate_limit)
    output_csv = output_csv or f"redirects_{_timestamp()}.csv"
    pd.DataFrame([r.model_dump() for r in results]).to_csv(
        output_csv, index=False, encoding="utf-8"
    )
    flagged = sum(1 for r in results if r.remark)
    return {
        "mapped": len(results),
        "flagged_for_review": flagged,
        "output_csv": output_csv,
    }


@tool
def cluster_keywords(
    keywords: list[str],
    method: str = "kmeans",
    output_csv: str = "",
) -> dict:
    """Cluster a list of keywords semantically using OpenAI embeddings + sklearn.

    Costs OpenAI tokens (small but real). Hard cap of 500 keywords without
    explicit re-confirmation.

    Args:
        keywords: Keyword strings to cluster.
        method: ``"kmeans"`` | ``"agglomerative"`` | ``"dbscan"`` | ``"spectral"``.
        output_csv: Optional output path. If omitted, timestamped.
    """
    if len(keywords) > 500:
        raise ValueError(
            "Cluster cap exceeded (500). Re-confirm before running on more keywords."
        )
    settings = Settings()
    if not settings.openai_api_key:
        raise ValueError(
            "Keyword clustering requires SEO_BHISHMA_OPENAI_API_KEY."
        )
    try:
        cluster_method = ClusterMethod(method.lower())
    except ValueError as e:
        raise ValueError(
            f"Unknown method: {method}. Use kmeans / agglomerative / dbscan / spectral."
        ) from e
    vectors = _ks.generate_vector_embeddings(keywords, settings.openai_api_key)
    result = _ks.cluster_keywords_vectors(keywords, vectors, method=cluster_method)
    output_csv = output_csv or f"clusters_{_timestamp()}.csv"
    pd.DataFrame(
        {
            "keyword": result.keywords,
            "cluster_label": result.labels,
            "cluster_name": [result.cluster_names[label] for label in result.labels],
        }
    ).to_csv(output_csv, index=False, encoding="utf-8")
    return {
        "keywords": len(keywords),
        "clusters": result.num_clusters,
        "silhouette_score": result.silhouette_score,
        "output_csv": output_csv,
    }


@tool
def detect_cannibalization(
    input_csv: str,
    output_csv: str = "",
    use_semantic_check: bool = False,
) -> dict:
    """Detect URL cannibalization in a GSC export (page, query, clicks, impressions, ctr, position).

    ``use_semantic_check=True`` enables sentence-transformer embeddings —
    significantly slower but catches near-duplicate intent across pages.
    """
    config = CannibalizationConfig(use_semantic_check=use_semantic_check)
    report = _hannibal.detect_cannibalization(input_csv, config=config)
    output_csv = output_csv or f"cannibalization_{_timestamp()}.csv"
    pd.DataFrame([e.model_dump() for e in report.entries]).to_csv(
        output_csv, index=False, encoding="utf-8"
    )
    return {
        "pages_analyzed": report.total_pages_analyzed,
        "clusters": report.total_clusters,
        "entries": len(report.entries),
        "competing_pairs": sum(
            1 for e in report.entries if e.action == "Merge into Primary URL"
        ),
        "output_csv": output_csv,
    }


# ---------------------------------------------------------------------------
# File-writing tools (auth tier: "confirm_each")
# ---------------------------------------------------------------------------


@tool
def generate_sitemap(
    urls: list[str],
    output_path: str = "",
    priority: str = "",
    changefreq: str = "",
    lastmod: str = "",
    compressed: bool = False,
) -> dict:
    """Generate an XML sitemap from a list of URLs and write to a file.

    Args:
        urls: URLs to include.
        output_path: Output filename. If empty, a timestamped sitemap.xml is used.
        priority / changefreq / lastmod: Optional defaults applied to all URLs.
        compressed: Gzip the output.
    """
    content = _sg.generate_sitemap(
        urls,
        priority=priority or None,
        frequency=changefreq or None,
        lastmod=lastmod or None,
    )
    output_path = output_path or f"sitemap_{_timestamp()}.xml" + (".gz" if compressed else "")
    _sg.write_sitemap(output_path, content, compressed=compressed)
    return {"urls": len(urls), "output_path": output_path}


@tool
def generate_nested_sitemaps(
    urls: list[str],
    output_dir: str,
    url_limit: int = 50000,
    compressed: bool = False,
) -> dict:
    """Generate multiple sitemaps + a sitemap index for a large URL set.

    Each sitemap holds at most ``url_limit`` URLs. Outputs go in ``output_dir``.
    """
    files, index_path = _sg.generate_nested_sitemaps(
        urls,
        output_dir=output_dir,
        url_limit=url_limit,
        compressed=compressed,
    )
    return {
        "urls": len(urls),
        "sitemap_files": files,
        "index_path": index_path,
    }


# ---------------------------------------------------------------------------
# Registry + authorization tiers
# ---------------------------------------------------------------------------


_AUTO: list = [
    check_backlink,
    get_dns_records,
    get_whois_info,
    get_ssl_certificate,
    get_security_headers,
    fetch_robots_txt,
    tech_stack_analysis,
    get_ip_address,
    get_ip_details,
    check_indexing_status,
    discover_sitemaps,
    parse_sitemap,
    gsc_list_sites,
]

_CONFIRM_ONCE: list = [
    batch_check_backlinks,
    batch_check_indexing,
    gsc_fetch_search_analytics,
    gsc_fetch_sitemaps,
    find_subdomains,
    map_redirect_urls,
    cluster_keywords,
    detect_cannibalization,
]

_CONFIRM_EACH: list = [
    generate_sitemap,
    generate_nested_sitemaps,
]


def _tag(tools: list, tier: str) -> list:
    for t in tools:
        # ``BaseTool.metadata`` is a writeable dict on LangChain ``StructuredTool``s.
        meta = dict(t.metadata or {})
        meta["auth_tier"] = tier
        t.metadata = meta
    return tools


_tag(_AUTO, "auto")
_tag(_CONFIRM_ONCE, "confirm_once")
_tag(_CONFIRM_EACH, "confirm_each")


ALL_TOOLS: list = _AUTO + _CONFIRM_ONCE + _CONFIRM_EACH


def get_auth_tier(tool_name: str) -> str:
    """Return the authorization tier for a tool by name. Defaults to ``"confirm_each"``."""
    for t in ALL_TOOLS:
        if t.name == tool_name:
            return (t.metadata or {}).get("auth_tier", "confirm_each")
    return "confirm_each"


# Re-export Pydantic models that callers may need to build inputs.
__all__ = [
    "ALL_TOOLS",
    "BacklinkCheckRequest",
    "get_auth_tier",
]


def _unused_import_anchor() -> Any:
    """Keep ``BacklinkCheckRequest`` reachable from ``ALL_TOOLS`` callers."""
    return BacklinkCheckRequest
