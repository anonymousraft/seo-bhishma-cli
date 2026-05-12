from seo_bhishma.models.index_spy import (
    BatchIndexCheckResult,
    CaptchaConfig,
    CaptchaHandling,
    CheckMethod,
    IndexCheckResult,
    ProxyConfig,
)
from seo_bhishma.core.index_spy import _parse_indexing_html


def test_check_method_enum():
    assert CheckMethod.HTML_SESSION == "htmlsession"
    assert CheckMethod.PLAYWRIGHT == "playwright"


def test_captcha_handling_enum():
    assert CaptchaHandling.BY_USER == "by_user"
    assert CaptchaHandling.AUTOMATIC == "automatic"


def test_proxy_config():
    config = ProxyConfig(proxy_list=["1.2.3.4:8080", "5.6.7.8:3128"])
    assert len(config.proxy_list) == 2
    assert config.mode == ["http", "https"]


def test_captcha_config():
    config = CaptchaConfig(service="2captcha", api_key="test-key")
    assert config.service == "2captcha"


def test_index_check_result():
    result = IndexCheckResult(url="https://example.com", status="Indexed")
    assert result.proxy_used == "No Proxy"


def test_batch_index_check_result():
    result = BatchIndexCheckResult(
        results=[
            IndexCheckResult(url="https://a.com", status="Indexed"),
            IndexCheckResult(url="https://b.com", status="Not Indexed"),
            IndexCheckResult(url="https://c.com", status="Error: timeout"),
        ],
        total_checked=3,
        total_indexed=1,
        total_not_indexed=1,
        total_errors=1,
    )
    assert result.total_checked == 3


def test_parse_indexing_html_not_indexed():
    html = '<html><body><p role="heading">Your search did not match any documents</p></body></html>'
    assert _parse_indexing_html(html, "https://example.com") == "Not Indexed"


def test_parse_indexing_html_captcha():
    html = "<html><body>Please solve the CAPTCHA to continue</body></html>"
    assert _parse_indexing_html(html, "https://example.com") == "Captcha Encountered"


def test_parse_indexing_html_indexed():
    html = '<html><body><div class="g"><a href="https://example.com/page">Example</a></div></body></html>'
    assert _parse_indexing_html(html, "https://example.com/page") == "Indexed"
