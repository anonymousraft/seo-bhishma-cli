"""Core domain information gathering logic. No CLI dependencies."""

import datetime
import logging
import re
import socket
import ssl
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from seo_bhishma.core._http import DEFAULT_TIMEOUT, generate_headers, requests_retry_session
from seo_bhishma.core._utils import extract_domain
from seo_bhishma.models.domain_insight import (
    DnsRecords,
    IpDetails,
    ReverseIpResult,
    RobotsCheckResult,
    RobotsTxtResult,
    SecurityHeadersResult,
    SslCertificateInfo,
    TechStackResult,
    WhoisInfo,
)

logger = logging.getLogger(__name__)

# Headers considered for the security audit (case-insensitive)
SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "x-xss-protection",
)


def is_valid_domain_or_url(input_string: str) -> bool:
    """Validate whether a string is a valid domain or URL.

    Accepts long TLDs (e.g. ``.museum``, ``.travel``) and Punycode TLDs.

    Args:
        input_string: Domain name or URL to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not input_string or " " in input_string.strip():
        return False
    domain_regex = re.compile(
        r"^(?:https?://)?(?:[a-zA-Z0-9-]{1,63}\.)+"
        r"(?:xn--[a-zA-Z0-9-]{1,59}|[a-zA-Z]{2,63})"
        r"(?::\d{1,5})?(?:[/?#]\S*)?$"
    )
    return domain_regex.match(input_string.strip()) is not None


def get_ip_address(domain: str) -> str | None:
    """Resolve a domain to its IP address.

    Args:
        domain: Domain name.

    Returns:
        IP address string, or None on failure.
    """
    try:
        return socket.gethostbyname(domain)
    except Exception as e:
        logger.error("Error retrieving IP address for %s: %s", domain, e)
        return None


def get_dns_records(domain: str) -> DnsRecords:
    """Fetch DNS records for a domain.

    Args:
        domain: Domain name.

    Returns:
        DnsRecords with A, AAAA, MX, NS, TXT, CNAME records.
    """
    import dns.resolver

    records = DnsRecords()
    resolver = dns.resolver.Resolver()
    record_map = {
        "A": "a",
        "AAAA": "aaaa",
        "MX": "mx",
        "NS": "ns",
        "TXT": "txt",
        "CNAME": "cname",
    }

    for record_type, field_name in record_map.items():
        try:
            answers = resolver.resolve(domain, record_type)
            setattr(records, field_name, [str(answer) for answer in answers])
        except (
            dns.resolver.NoAnswer,
            dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers,
        ):
            pass
        except Exception as e:
            logger.warning("Error fetching %s records for %s: %s", record_type, domain, e)

    return records


def get_whois_info(domain: str) -> WhoisInfo:
    """Fetch WHOIS information for a domain.

    Args:
        domain: Domain name.

    Returns:
        WhoisInfo with formatted WHOIS data.
    """
    import whois

    domain_clean = extract_domain(f"https://{domain}") or domain

    try:
        info = whois.whois(domain_clean)
        formatted: dict[str, str] = {}
        for key, value in info.items():
            if isinstance(value, list):
                formatted[key] = ", ".join(str(v) for v in value)
            elif isinstance(value, datetime.datetime):
                formatted[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted[key] = str(value) if value is not None else ""
        return WhoisInfo(data=formatted)
    except Exception as e:
        logger.error("Error retrieving WHOIS information: %s", e)
        return WhoisInfo(data={})


def get_ip_details(ip: str) -> IpDetails:
    """Get detailed IP information including ASN and geolocation.

    Args:
        ip: IP address.

    Returns:
        IpDetails with ASN and geo data.
    """
    details = IpDetails(ip=ip)

    try:
        from ipwhois import IPWhois

        obj = IPWhois(ip)
        results = obj.lookup_rdap()
        details.asn = str(results.get("asn", ""))
        details.asn_country_code = str(results.get("asn_country_code", ""))
        details.asn_date = str(results.get("asn_date", ""))
        details.asn_description = str(results.get("asn_description", ""))
        details.asn_cidr = str(results.get("asn_cidr", ""))
        details.asn_registry = str(results.get("asn_registry", ""))
    except Exception as e:
        logger.error("Error retrieving ASN details: %s", e)

    try:
        response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=10)
        if response.status_code == 200:
            data = response.json()
            details.hostname = data.get("hostname", "")
            details.city = data.get("city", "")
            details.region = data.get("region", "")
            details.country = data.get("country", "")
            details.location = data.get("loc", "")
            details.organization = data.get("org", "")
            details.postal = data.get("postal", "")
            details.timezone = data.get("timezone", "")
    except Exception as e:
        logger.error("Error retrieving ipinfo.io details: %s", e)

    return details


def find_subdomains(domain: str, threads: int = 40) -> list[str]:
    """Find subdomains using sublist3r.

    Args:
        domain: Domain name.
        threads: Number of threads for enumeration.

    Returns:
        List of discovered subdomains.
    """
    try:
        import sublist3r

        subdomains = sublist3r.main(
            domain,
            threads,
            savefile=None,
            ports=None,
            silent=True,
            verbose=False,
            enable_bruteforce=False,
            engines=None,
        )
        return subdomains or []
    except Exception as e:
        logger.error("Error finding subdomains: %s", e)
        return []


def tech_analysis(domain: str) -> TechStackResult:
    """Detect technologies used by a website.

    Tolerant of Wappalyzer package import variations (``Wappalyzer`` vs
    ``wappalyzer``).

    Args:
        domain: Domain name.

    Returns:
        TechStackResult with detected technologies.
    """
    try:
        try:
            from Wappalyzer import Wappalyzer, WebPage  # type: ignore
        except ImportError:
            from wappalyzer import Wappalyzer, WebPage  # type: ignore

        url = f"https://{domain}"
        wappalyzer = Wappalyzer.latest()
        webpage = WebPage.new_from_url(url)
        technologies = list(wappalyzer.analyze(webpage))
        return TechStackResult(domain=domain, technologies=technologies)
    except Exception as e:
        logger.error("Error analyzing tech stack for %s: %s", domain, e)
        return TechStackResult(domain=domain, technologies=[])


def get_ssl_certificate(domain: str, port: int = 443, timeout: int = 10) -> SslCertificateInfo:
    """Fetch and parse the TLS certificate for a domain.

    Args:
        domain: Bare domain name.
        port: TLS port (default 443).
        timeout: Socket timeout in seconds.

    Returns:
        ``SslCertificateInfo`` (``.error`` is populated on failure).
    """
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()

        def _flatten(items) -> dict[str, str]:
            out: dict[str, str] = {}
            for entry in items or []:
                for k, v in entry:
                    out[k] = v
            return out

        sans = [v for k, v in (cert.get("subjectAltName") or []) if k == "DNS"]
        return SslCertificateInfo(
            domain=domain,
            issuer=_flatten(cert.get("issuer")),
            subject=_flatten(cert.get("subject")),
            valid_from=cert.get("notBefore", ""),
            valid_to=cert.get("notAfter", ""),
            serial_number=str(cert.get("serialNumber", "")),
            version=cert.get("version"),
            subject_alt_names=sans,
        )
    except Exception as e:
        logger.error("Error fetching SSL certificate for %s: %s", domain, e)
        return SslCertificateInfo(domain=domain, error=str(e))


def get_security_headers(domain: str) -> SecurityHeadersResult:
    """Fetch and grade HTTP security response headers for a domain.

    Grade scale: A (>=6 of 7 expected), B (5), C (4), D (2-3), F (<=1).
    """
    url = f"https://{domain}"
    try:
        session = requests_retry_session()
        r = session.get(url, headers=generate_headers(), timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        headers_ci = {k.lower(): v for k, v in r.headers.items()}
        present = {h: headers_ci[h] for h in SECURITY_HEADERS if h in headers_ci}
        missing = [h for h in SECURITY_HEADERS if h not in headers_ci]
        n = len(present)
        if n >= 6:
            grade = "A"
        elif n == 5:
            grade = "B"
        elif n == 4:
            grade = "C"
        elif n >= 2:
            grade = "D"
        else:
            grade = "F"
        return SecurityHeadersResult(
            domain=domain,
            url=r.url,
            status_code=r.status_code,
            headers=present,
            grade=grade,
            missing=missing,
        )
    except Exception as e:
        logger.error("Error fetching security headers for %s: %s", domain, e)
        return SecurityHeadersResult(domain=domain, url=url, error=str(e), missing=list(SECURITY_HEADERS), grade="F")


def fetch_robots_txt(domain: str) -> RobotsTxtResult | None:
    """Fetch and parse robots.txt for a domain using HTTP requests.

    Tries multiple URL variations (https/http, with/without www).

    Args:
        domain: Domain name.

    Returns:
        RobotsTxtResult, or None if not found.
    """
    urls = [
        f"https://{domain}/robots.txt",
        f"http://{domain}/robots.txt",
        f"https://www.{domain}/robots.txt",
        f"http://www.{domain}/robots.txt",
    ]

    headers = generate_headers()

    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200 and response.text.strip():
                content = response.text
                disallows, sitemaps = parse_robots_txt(content)
                return RobotsTxtResult(
                    raw_content=content,
                    disallow_rules=disallows,
                    sitemaps=sitemaps,
                )
        except Exception as e:
            logger.debug("Error fetching robots.txt from %s: %s", url, e)

    return None


async def fetch_robots_txt_playwright(domain: str) -> RobotsTxtResult | None:
    """Fetch robots.txt using Playwright (for JS-rendered or protected sites).

    Args:
        domain: Domain name.

    Returns:
        RobotsTxtResult, or None if not found.
    """
    from playwright.async_api import async_playwright

    urls = [
        f"https://{domain}/robots.txt",
        f"http://{domain}/robots.txt",
        f"https://www.{domain}/robots.txt",
        f"http://www.{domain}/robots.txt",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for url in urls:
            try:
                await page.goto(url)
                await page.wait_for_selector("pre", timeout=10000)
                pre = await page.query_selector("pre")
                if pre:
                    content = await pre.inner_text()
                    if content:
                        await browser.close()
                        disallows, sitemaps = parse_robots_txt(content)
                        return RobotsTxtResult(
                            raw_content=content,
                            disallow_rules=disallows,
                            sitemaps=sitemaps,
                        )
            except Exception as e:
                logger.debug("Error fetching robots.txt from %s via Playwright: %s", url, e)

        await browser.close()

    return None


def parse_robots_txt(content: str) -> tuple[list[str], list[str]]:
    """Parse robots.txt content into disallow rules and sitemap URLs.

    Args:
        content: Raw robots.txt content.

    Returns:
        Tuple of (disallow_rules, sitemap_urls).
    """
    disallows: list[str] = []
    sitemaps: list[str] = []

    for line in content.splitlines():
        line = line.strip()
        if line.lower().startswith("disallow"):
            parts = line.split(": ", 1)
            if len(parts) == 2 and parts[1].strip():
                disallows.append(parts[1].strip())
        elif line.lower().startswith("sitemap"):
            parts = line.split(": ", 1)
            if len(parts) == 2 and parts[1].strip():
                sitemaps.append(parts[1].strip())

    return disallows, sitemaps


def check_urls_against_robots(
    disallow_rules: list[str],
    urls: list[tuple[str, str]],
) -> list[RobotsCheckResult]:
    """Check a list of URLs against robots.txt disallow rules.

    Args:
        disallow_rules: List of disallow path patterns.
        urls: List of (sitemap_url, page_url) tuples.

    Returns:
        List of RobotsCheckResult for each URL.
    """
    results: list[RobotsCheckResult] = []

    for sitemap_url, url in urls:
        # Extract path from full URL for comparison against disallow rules
        url_path = urlparse(url).path or url
        blocked = False
        for rule in disallow_rules:
            if rule != "/" and url_path.startswith(rule):
                results.append(
                    RobotsCheckResult(
                        sitemap_url=sitemap_url,
                        url=url,
                        matching_rule=rule,
                        status="Blocked",
                    )
                )
                blocked = True
                break
        if not blocked:
            results.append(
                RobotsCheckResult(
                    sitemap_url=sitemap_url,
                    url=url,
                    status="Not Blocked",
                )
            )

    return results


async def reverse_ip_lookup_playwright(ip: str) -> ReverseIpResult | None:
    """Perform reverse IP lookup using Playwright to scrape tntcode.com.

    Args:
        ip: IP address.

    Returns:
        ReverseIpResult, or None on failure.
    """
    from playwright.async_api import async_playwright

    url = f"https://domains.tntcode.com/ip/{ip}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(url)

            # Wait for content or CAPTCHA
            while True:
                title = await page.title()
                if "Captcha" in title:
                    logger.info("CAPTCHA detected. Waiting for user to solve...")
                    while "Captcha" in await page.title():
                        try:
                            await page.wait_for_selector("body", timeout=10000)
                        except Exception:
                            await browser.close()
                            return None
                try:
                    await page.wait_for_selector("table", timeout=20000)
                    break
                except Exception:
                    content = await page.content()
                    if "not found" in content.lower():
                        await browser.close()
                        return None
                    if "verifying you are human" not in content.lower():
                        break
                    await page.wait_for_selector("body", timeout=20000)

            page_source = await page.content()
            await browser.close()

            if not page_source:
                return None

            # Parse the page
            soup = BeautifulSoup(page_source, "html.parser")
            h1 = soup.find("h1")
            title_text = h1.get_text() if h1 else ""

            table = soup.find("table")
            table_info: dict[str, str] = {}
            if table:
                for row in table.find_all("tr"):
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        table_info[cols[0].get_text().strip()] = cols[1].get_text().strip()

            textarea = soup.find("textarea")
            domains = (
                textarea.get_text().strip().split("\n") if textarea else []
            )

            return ReverseIpResult(
                title=title_text,
                table_info=table_info,
                domains=domains,
            )

    except Exception as e:
        logger.error("Error performing reverse IP lookup: %s", e)
        return None
