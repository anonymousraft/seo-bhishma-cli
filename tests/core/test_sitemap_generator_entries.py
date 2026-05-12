"""Tests for per-URL UrlEntry support in sitemap generation."""

from seo_bhishma.core.sitemap_generator import generate_sitemap
from seo_bhishma.models.sitemap_generator import SitemapImage, UrlEntry


def test_generate_sitemap_with_entry_overrides():
    entry = UrlEntry(
        loc="https://example.com/special",
        priority="1.0",
        changefreq="hourly",
        lastmod="2025-06-01",
    )
    xml = generate_sitemap([entry], priority="0.5", frequency="daily", lastmod="2025-01-01").decode()
    assert "https://example.com/special" in xml
    assert "<priority>1.0</priority>" in xml
    assert "<changefreq>hourly</changefreq>" in xml
    assert "<lastmod>2025-06-01</lastmod>" in xml
    # Generator defaults should not leak in for this URL
    assert "<priority>0.5</priority>" not in xml


def test_generate_sitemap_mixed_str_and_entry():
    urls = [
        "https://example.com/plain",
        UrlEntry(loc="https://example.com/typed", priority="0.9"),
    ]
    xml = generate_sitemap(urls, priority="0.5").decode()
    assert "https://example.com/plain" in xml
    assert "https://example.com/typed" in xml
    assert "<priority>0.9</priority>" in xml
    assert "<priority>0.5</priority>" in xml  # default applied to plain URL


def test_generate_sitemap_with_image():
    entry = UrlEntry(
        loc="https://example.com/page",
        images=[SitemapImage(loc="https://example.com/img.jpg", caption="Alt")],
    )
    xml = generate_sitemap([entry]).decode()
    assert "https://example.com/img.jpg" in xml
    assert "Alt" in xml
    assert "sitemap-image" in xml


def test_generate_sitemap_with_stylesheet():
    xml = generate_sitemap(
        ["https://example.com/"], stylesheet="https://example.com/sitemap.xsl"
    ).decode()
    assert 'xml-stylesheet' in xml
    assert "sitemap.xsl" in xml
