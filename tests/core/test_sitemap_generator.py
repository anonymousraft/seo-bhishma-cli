import tempfile
from pathlib import Path

from seo_bhishma.core.sitemap_generator import (
    generate_nested_sitemaps,
    generate_sitemap,
    generate_sitemap_index,
)


def test_generate_sitemap_basic():
    urls = ["https://example.com/page1", "https://example.com/page2"]
    result = generate_sitemap(urls)
    xml_str = result.decode("utf-8")
    assert "https://example.com/page1" in xml_str
    assert "https://example.com/page2" in xml_str
    assert "<urlset" in xml_str


def test_generate_sitemap_with_options():
    urls = ["https://example.com/"]
    result = generate_sitemap(urls, priority="0.8", frequency="daily", lastmod="2025-01-01")
    xml_str = result.decode("utf-8")
    assert "<priority>0.8</priority>" in xml_str
    assert "<changefreq>daily</changefreq>" in xml_str
    assert "<lastmod>2025-01-01</lastmod>" in xml_str


def test_generate_sitemap_index():
    locs = ["sitemap_0.xml", "sitemap_1.xml"]
    result = generate_sitemap_index(locs)
    xml_str = result.decode("utf-8")
    assert "<sitemapindex" in xml_str
    assert "sitemap_0.xml" in xml_str
    assert "sitemap_1.xml" in xml_str


def test_generate_nested_sitemaps():
    urls = [f"https://example.com/page{i}" for i in range(10)]
    with tempfile.TemporaryDirectory() as tmpdir:
        files, index_path = generate_nested_sitemaps(
            urls, tmpdir, url_limit=3, compressed=False
        )
        assert len(files) == 4  # 10 URLs / 3 per sitemap = 4 sitemaps
        assert Path(index_path).exists()
        for f in files:
            assert Path(f).exists()
