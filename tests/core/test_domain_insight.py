from seo_bhishma.core.domain_insight import (
    check_urls_against_robots,
    is_valid_domain_or_url,
    parse_robots_txt,
)
from seo_bhishma.models.domain_insight import (
    DnsRecords,
    IpDetails,
    RobotsTxtResult,
    TechStackResult,
)


def test_is_valid_domain():
    assert is_valid_domain_or_url("example.com") is True
    assert is_valid_domain_or_url("https://www.example.com") is True
    assert is_valid_domain_or_url("not a domain") is False
    assert is_valid_domain_or_url("") is False


def test_parse_robots_txt():
    content = """User-agent: *
Disallow: /admin/
Disallow: /private/
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap2.xml"""

    disallows, sitemaps = parse_robots_txt(content)
    assert disallows == ["/admin/", "/private/"]
    assert sitemaps == ["https://example.com/sitemap.xml", "https://example.com/sitemap2.xml"]


def test_check_urls_against_robots():
    disallows = ["/admin/", "/private/"]
    urls = [
        ("sitemap.xml", "https://example.com/admin/page"),
        ("sitemap.xml", "https://example.com/public/page"),
        ("sitemap.xml", "https://example.com/private/secret"),
    ]
    results = check_urls_against_robots(disallows, urls)
    assert len(results) == 3
    assert results[0].status == "Blocked"
    assert results[0].matching_rule == "/admin/"
    assert results[1].status == "Not Blocked"
    assert results[2].status == "Blocked"


def test_dns_records_model():
    records = DnsRecords(a=["1.2.3.4"], mx=["mail.example.com"])
    assert records.a == ["1.2.3.4"]
    assert records.aaaa == []


def test_ip_details_model():
    details = IpDetails(ip="1.2.3.4", city="San Francisco", country="US")
    assert details.ip == "1.2.3.4"
    assert details.asn == ""


def test_tech_stack_result():
    result = TechStackResult(domain="example.com", technologies=["WordPress", "PHP"])
    assert len(result.technologies) == 2


def test_robots_txt_result():
    result = RobotsTxtResult(
        raw_content="Disallow: /admin/",
        disallow_rules=["/admin/"],
        sitemaps=[],
    )
    assert len(result.disallow_rules) == 1
