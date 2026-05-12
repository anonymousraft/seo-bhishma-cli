from pydantic import BaseModel


class SitemapUrl(BaseModel):
    """A single URL entry parsed from a sitemap."""

    sitemap_name: str
    loc: str
    lastmod: str = ""
    changefreq: str = ""
    priority: str = ""
    images: list[dict[str, str]] = []
    videos: list[dict[str, str]] = []
    news: list[dict[str, str]] = []


class SitemapParseResult(BaseModel):
    """Result of parsing a complete sitemap (including nested)."""

    urls: list[SitemapUrl]
    total_sitemaps_parsed: int = 1
