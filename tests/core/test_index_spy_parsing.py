"""Extended tests for the indexing-status HTML parser."""

from seo_bhishma.core.index_spy import _parse_indexing_html


def test_parse_indexing_unusual_traffic_captcha():
    html = "<html><body>Our systems have detected unusual traffic from your computer.</body></html>"
    assert _parse_indexing_html(html, "https://example.com") == "Captcha Encountered"


def test_parse_indexing_sorry_redirect():
    html = "<html><body><meta http-equiv='refresh' content='0; url=/sorry/index'></body></html>"
    assert _parse_indexing_html(html, "https://example.com") == "Captcha Encountered"


def test_parse_indexing_tf2cxc_class():
    html = """
    <html><body>
      <div class="tF2Cxc"><a href="https://example.com/page">Example page</a></div>
    </body></html>
    """
    assert _parse_indexing_html(html, "https://example.com/page") == "Indexed"


def test_parse_indexing_data_hveid_fallback():
    html = """
    <html><body>
      <div data-hveid="123"><a href="https://example.com/article">Article</a></div>
    </body></html>
    """
    assert _parse_indexing_html(html, "https://example.com/article") == "Indexed"


def test_parse_indexing_bare_anchor_fallback():
    html = '<html><body><a href="https://example.com/foo">foo</a></body></html>'
    assert _parse_indexing_html(html, "https://example.com/foo") == "Indexed"


def test_parse_indexing_empty_results():
    html = "<html><body></body></html>"
    assert _parse_indexing_html(html, "https://example.com") == "Not Indexed"
