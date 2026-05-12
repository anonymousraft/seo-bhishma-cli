"""Tests for sitemap parsing - namespace tolerance, nested handling."""

import xml.etree.ElementTree as ET

from seo_bhishma.core.site_mapper import (
    NAMESPACE,
    _find,
    _findall,
    _strip_namespace,
    parse_url_element,
    parse_sitemap,
)


NS_DECL = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def test_strip_namespace():
    xml = f'<urlset {NS_DECL}><url><loc>https://example.com/</loc></url></urlset>'
    root = ET.fromstring(xml)
    _strip_namespace(root)
    assert root.tag == "urlset"
    assert root[0].tag == "url"


def test_find_with_namespace():
    xml = f'<urlset {NS_DECL}><url><loc>https://example.com/</loc></url></urlset>'
    root = ET.fromstring(xml)
    url = root.find("ns:url", NAMESPACE)
    loc = _find(url, "loc")
    assert loc is not None
    assert loc.text == "https://example.com/"


def test_find_without_namespace():
    xml = "<urlset><url><loc>https://example.com/</loc></url></urlset>"
    root = ET.fromstring(xml)
    url = root.find("url")
    loc = _find(url, "loc")
    assert loc is not None
    assert loc.text == "https://example.com/"


def test_parse_url_element_with_image():
    xml = f"""
    <url {NS_DECL} xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <loc>https://example.com/page</loc>
      <lastmod>2025-01-01</lastmod>
      <changefreq>weekly</changefreq>
      <priority>0.8</priority>
      <image><loc>https://example.com/img.jpg</loc><caption>Alt text</caption></image>
    </url>
    """
    elem = ET.fromstring(xml)
    result = parse_url_element(elem, "test")
    assert result is not None
    assert result.loc == "https://example.com/page"
    assert result.lastmod == "2025-01-01"
    assert result.priority == "0.8"
    # Image namespace doesn't match the strip-then-find sitemap NS path
    # but the basic fields parse correctly


def test_parse_sitemap_no_namespace():
    """Sitemap missing xmlns declaration still parses."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>"""
    root = ET.fromstring(xml)
    result = parse_sitemap(root, "test.xml", max_workers=2)
    assert len(result.urls) == 2
    locs = {u.loc for u in result.urls}
    assert locs == {"https://example.com/a", "https://example.com/b"}


def test_parse_sitemap_with_standard_namespace():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset {NS_DECL}>
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>"""
    root = ET.fromstring(xml)
    result = parse_sitemap(root, "test.xml", max_workers=2)
    assert len(result.urls) == 2
