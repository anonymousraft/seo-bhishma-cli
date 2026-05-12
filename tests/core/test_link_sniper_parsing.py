"""Tests for backlink HTML parsing logic (no network)."""

from unittest.mock import patch

from seo_bhishma.core.link_sniper import NOFOLLOW_REL_VALUES, _rel_attrs, check_backlink


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_rel_attrs_string_form():
    class _Tag:
        def get(self, _: str):
            return "nofollow sponsored"

    assert _rel_attrs(_Tag()) == ["nofollow", "sponsored"]


def test_rel_attrs_list_form():
    class _Tag:
        def get(self, _: str):
            return ["nofollow", "ugc"]

    assert _rel_attrs(_Tag()) == ["nofollow", "ugc"]


def test_rel_attrs_missing():
    class _Tag:
        def get(self, _: str):
            return None

    assert _rel_attrs(_Tag()) == []


def test_check_backlink_nofollow_detection():
    html = """
    <html><body>
      <a href="https://target.com" rel="nofollow sponsored">click here</a>
    </body></html>
    """
    with patch("seo_bhishma.core.link_sniper.requests_retry_session") as mock_sess:
        mock_sess.return_value.get.return_value = _FakeResponse(200, html)
        result = check_backlink("https://example.com", "https://target.com", "click here")

    assert result.status == "Live"
    assert result.link_exists == "Yes"
    assert result.anchor_status == "Present"
    assert result.http_status == 200
    assert "nofollow" in result.rel_values
    assert "sponsored" in result.rel_values
    assert result.is_dofollow is False
    assert any(v in NOFOLLOW_REL_VALUES for v in result.rel_values)


def test_check_backlink_dofollow_default():
    html = '<html><body><a href="https://target.com">anchor</a></body></html>'
    with patch("seo_bhishma.core.link_sniper.requests_retry_session") as mock_sess:
        mock_sess.return_value.get.return_value = _FakeResponse(200, html)
        result = check_backlink("https://example.com", "https://target.com")

    assert result.is_dofollow is True
    assert result.rel_values == []


def test_check_backlink_404():
    with patch("seo_bhishma.core.link_sniper.requests_retry_session") as mock_sess:
        mock_sess.return_value.get.return_value = _FakeResponse(404, "Not Found")
        result = check_backlink("https://example.com/x", "https://target.com")

    assert result.status == "Not Live"
    assert result.http_status == 404
    assert result.link_exists == "No"


def test_check_backlink_not_found():
    html = '<html><body><a href="https://other.com">other</a></body></html>'
    with patch("seo_bhishma.core.link_sniper.requests_retry_session") as mock_sess:
        mock_sess.return_value.get.return_value = _FakeResponse(200, html)
        result = check_backlink("https://example.com", "https://target.com")

    assert result.status == "Not Found"
    assert result.link_exists == "No"
