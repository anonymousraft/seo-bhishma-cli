from pydantic import BaseModel


class SitemapImage(BaseModel):
    """An image associated with a sitemap URL entry."""

    loc: str
    caption: str = ""
    title: str = ""


class SitemapNews(BaseModel):
    """News metadata for a sitemap URL entry."""

    title: str
    publication_name: str
    publication_language: str = "en"
    publication_date: str = ""


class UrlEntry(BaseModel):
    """A single URL entry with optional per-URL metadata.

    When generating, ``priority``/``changefreq``/``lastmod`` set on the entry
    take precedence over generator-level defaults.
    """

    loc: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: str | None = None
    images: list[SitemapImage] = []
    news: list[SitemapNews] = []


class SitemapConfig(BaseModel):
    """Configuration for sitemap generation."""

    urls: list[str]
    priority: str | None = None
    frequency: str | None = None
    lastmod: str | None = None
    compressed: bool = False


class SitemapIndexConfig(BaseModel):
    """Configuration for nested sitemap generation."""

    urls: list[str]
    url_limit: int = 50000
    priority: str | None = None
    frequency: str | None = None
    lastmod: str | None = None
    compressed: bool = False
