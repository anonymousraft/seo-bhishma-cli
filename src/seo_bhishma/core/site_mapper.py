"""Core sitemap downloading and parsing logic. No CLI dependencies."""

import gzip
import logging
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from seo_bhishma.core._http import DEFAULT_TIMEOUT, requests_retry_session
from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.site_mapper import SitemapParseResult, SitemapUrl

logger = logging.getLogger(__name__)

NAMESPACE = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_NS_RE = re.compile(r"^\{[^}]+\}")


def _strip_namespace(tree: ET.Element) -> ET.Element:
    """Strip XML namespaces in-place so we can use ``ns:`` lookups uniformly."""
    for elem in tree.iter():
        if isinstance(elem.tag, str):
            elem.tag = _NS_RE.sub("", elem.tag)
    return tree


def _findall(elem: ET.Element, tag: str) -> list[ET.Element]:
    """Namespace-tolerant findall. Tries ``ns:tag`` then bare ``tag``."""
    found = elem.findall(f"ns:{tag}", NAMESPACE)
    if found:
        return found
    return elem.findall(tag)


def _find(elem: ET.Element, tag: str) -> ET.Element | None:
    """Namespace-tolerant find."""
    res = elem.find(f"ns:{tag}", NAMESPACE)
    if res is not None:
        return res
    return elem.find(tag)


def download_sitemap(url: str) -> ET.Element | None:
    """Download and parse a sitemap XML from a URL.

    Supports both plain .xml and .gz compressed sitemaps. Tolerates sitemaps
    missing the xmlns declaration.

    Args:
        url: Sitemap URL.

    Returns:
        Parsed XML root element, or None on failure.
    """
    try:
        response = requests_retry_session().get(url, stream=True, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        if url.endswith(".gz"):
            with gzip.GzipFile(fileobj=response.raw) as f:
                root = ET.parse(f).getroot()
        else:
            root = ET.fromstring(response.content)
        # If namespace is missing or non-standard, strip it so our lookups work
        if root.tag.startswith("{") and "sitemaps.org" not in root.tag:
            root = _strip_namespace(root)
        elif not root.tag.startswith("{"):
            # No namespace at all - lookups will fall back to bare tags
            pass
        return root
    except Exception as e:
        logger.error("Error downloading/parsing sitemap %s: %s", url, e)
        return None


def parse_url_element(url_elem: ET.Element, sitemap_name: str) -> SitemapUrl | None:
    """Parse a single <url> element from a sitemap.

    Args:
        url_elem: The XML <url> element.
        sitemap_name: Name/URL of the parent sitemap.

    Returns:
        SitemapUrl model, or None on parse failure.
    """
    try:
        loc_el = _find(url_elem, "loc")
        if loc_el is None or loc_el.text is None:
            return None

        def _text(tag: str) -> str:
            el = _find(url_elem, tag)
            return el.text if el is not None and el.text else ""

        images = []
        for img in _findall(url_elem, "image"):
            img_loc = _find(img, "loc")
            img_caption = _find(img, "caption")
            images.append({
                "loc": img_loc.text if img_loc is not None and img_loc.text else "",
                "caption": img_caption.text if img_caption is not None and img_caption.text else "",
            })

        videos = []
        for vid in _findall(url_elem, "video"):
            vid_loc = _find(vid, "content_loc")
            vid_title = _find(vid, "title")
            videos.append({
                "loc": vid_loc.text if vid_loc is not None and vid_loc.text else "",
                "title": vid_title.text if vid_title is not None and vid_title.text else "",
            })

        news = []
        for news_item in _findall(url_elem, "news"):
            pub_date = _find(news_item, "publication_date")
            title = _find(news_item, "title")
            news.append({
                "publication_date": pub_date.text if pub_date is not None and pub_date.text else "",
                "title": title.text if title is not None and title.text else "",
            })

        return SitemapUrl(
            sitemap_name=sitemap_name,
            loc=loc_el.text,
            lastmod=_text("lastmod"),
            changefreq=_text("changefreq"),
            priority=_text("priority"),
            images=images,
            videos=videos,
            news=news,
        )
    except Exception as e:
        logger.error("Error parsing URL element: %s", e)
        return None


def parse_sitemap(
    root: ET.Element,
    sitemap_name: str,
    max_workers: int = 10,
    on_progress: ProgressCallback | None = None,
) -> SitemapParseResult:
    """Parse a sitemap root element, recursively handling nested sitemaps.

    Args:
        root: The XML root element (urlset or sitemapindex).
        sitemap_name: Name/URL of this sitemap.
        max_workers: Thread pool size for parallel URL parsing.
        on_progress: Optional progress callback.

    Returns:
        SitemapParseResult with all parsed URLs.
    """
    urls: list[SitemapUrl] = []
    sitemaps_parsed = 1

    # Check for nested sitemaps (sitemapindex)
    nested = _findall(root, "sitemap")
    if nested:
        logger.info("Found %d nested sitemaps in %s", len(nested), sitemap_name)
        for sitemap_el in nested:
            loc_el = _find(sitemap_el, "loc")
            if loc_el is None or loc_el.text is None:
                continue
            child_root = download_sitemap(loc_el.text)
            if child_root:
                child_result = parse_sitemap(child_root, loc_el.text, max_workers, on_progress)
                urls.extend(child_result.urls)
                sitemaps_parsed += child_result.total_sitemaps_parsed
    else:
        # Parse URL elements
        url_elements = _findall(root, "url")
        total = len(url_elements)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(parse_url_element, elem, sitemap_name): elem
                for elem in url_elements
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    urls.append(result)
                completed += 1
                if on_progress:
                    on_progress(completed, total)

    return SitemapParseResult(urls=urls, total_sitemaps_parsed=sitemaps_parsed)


def download_and_parse_sitemap(
    sitemap_url: str,
    max_workers: int = 10,
    on_progress: ProgressCallback | None = None,
) -> SitemapParseResult | None:
    """Download and fully parse a sitemap, including nested sitemaps.

    This is the main entry point for sitemap parsing.

    Args:
        sitemap_url: URL of the sitemap.
        max_workers: Thread pool size.
        on_progress: Optional progress callback.

    Returns:
        SitemapParseResult, or None if download fails.
    """
    root = download_sitemap(sitemap_url)
    if root is None:
        return None
    result = parse_sitemap(root, sitemap_url, max_workers, on_progress)
    if len(result.urls) > 50000:
        # Spec recommends max 50k URLs per sitemap file (this is the aggregate)
        logger.warning(
            "Parsed %d URLs from %s - exceeds the 50,000 per-file sitemap spec limit",
            len(result.urls),
            sitemap_url,
        )
    return result


def discover_sitemaps_from_robots(domain: str) -> list[str]:
    """Discover sitemap URLs declared in a domain's robots.txt.

    Tries https/http and with/without www prefix. Falls back to
    ``/sitemap.xml`` when robots.txt yields no sitemap directives.

    Args:
        domain: Bare domain (no scheme), e.g. ``"example.com"``.

    Returns:
        Ordered list of discovered sitemap URLs (deduplicated).
    """
    candidates = [
        f"https://{domain}/robots.txt",
        f"https://www.{domain}/robots.txt",
        f"http://{domain}/robots.txt",
    ]
    session = requests_retry_session()
    discovered: list[str] = []
    seen: set[str] = set()
    fetched = False
    for url in candidates:
        try:
            r = session.get(url, timeout=DEFAULT_TIMEOUT)
            if r.status_code == 200 and r.text.strip():
                fetched = True
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap"):
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            sm = parts[1].strip()
                            if sm and sm not in seen:
                                seen.add(sm)
                                discovered.append(sm)
                break
        except Exception as e:
            logger.debug("robots.txt fetch failed for %s: %s", url, e)

    if not discovered:
        fallback = f"https://{domain}/sitemap.xml"
        if fetched:
            logger.info("No Sitemap: directive in robots.txt; falling back to %s", fallback)
        discovered.append(fallback)

    return discovered
