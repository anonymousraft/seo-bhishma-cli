"""Tests for the expanded domain_insight surface (validation, security headers)."""

from unittest.mock import MagicMock, patch

from seo_bhishma.core.domain_insight import (
    SECURITY_HEADERS,
    get_security_headers,
    is_valid_domain_or_url,
)


def test_is_valid_long_tld():
    assert is_valid_domain_or_url("example.museum") is True
    assert is_valid_domain_or_url("example.travel") is True
    assert is_valid_domain_or_url("sub.example.co.uk") is True
    assert is_valid_domain_or_url("https://example.io/path?q=1") is True


def test_is_valid_punycode_tld():
    # xn-- is the Punycode prefix for IDN TLDs
    assert is_valid_domain_or_url("example.xn--p1ai") is True


def test_is_valid_rejects_garbage():
    assert is_valid_domain_or_url("not a domain") is False
    assert is_valid_domain_or_url("") is False
    assert is_valid_domain_or_url("example") is False


def test_security_headers_grade_a():
    fake_headers = {h: "v" for h in SECURITY_HEADERS}
    mock_response = MagicMock(
        url="https://example.com/",
        status_code=200,
        headers=fake_headers,
    )
    with patch("seo_bhishma.core.domain_insight.requests_retry_session") as sess:
        sess.return_value.get.return_value = mock_response
        result = get_security_headers("example.com")

    assert result.grade == "A"
    assert result.missing == []
    assert result.status_code == 200


def test_security_headers_grade_f():
    mock_response = MagicMock(url="https://example.com/", status_code=200, headers={})
    with patch("seo_bhishma.core.domain_insight.requests_retry_session") as sess:
        sess.return_value.get.return_value = mock_response
        result = get_security_headers("example.com")

    assert result.grade == "F"
    assert len(result.missing) == len(SECURITY_HEADERS)


def test_security_headers_grade_c():
    fake_headers = {h: "v" for h in list(SECURITY_HEADERS)[:4]}
    mock_response = MagicMock(
        url="https://example.com/", status_code=200, headers=fake_headers
    )
    with patch("seo_bhishma.core.domain_insight.requests_retry_session") as sess:
        sess.return_value.get.return_value = mock_response
        result = get_security_headers("example.com")

    assert result.grade == "C"
    assert len(result.headers) == 4
