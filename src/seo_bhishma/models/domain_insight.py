"""Models for domain information gathering (Domain Insight)."""

from pydantic import BaseModel


class DnsRecords(BaseModel):
    """DNS records for a domain."""

    a: list[str] = []
    aaaa: list[str] = []
    mx: list[str] = []
    ns: list[str] = []
    txt: list[str] = []
    cname: list[str] = []


class WhoisInfo(BaseModel):
    """WHOIS information for a domain."""

    data: dict[str, str]


class IpDetails(BaseModel):
    """IP address details including ASN and geolocation."""

    ip: str
    asn: str = ""
    asn_country_code: str = ""
    asn_date: str = ""
    asn_description: str = ""
    asn_cidr: str = ""
    asn_registry: str = ""
    hostname: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    location: str = ""
    organization: str = ""
    postal: str = ""
    timezone: str = ""


class ReverseIpResult(BaseModel):
    """Result of a reverse IP lookup."""

    title: str = ""
    table_info: dict[str, str] = {}
    domains: list[str] = []


class RobotsTxtResult(BaseModel):
    """Parsed robots.txt information."""

    raw_content: str
    disallow_rules: list[str] = []
    sitemaps: list[str] = []


class RobotsCheckResult(BaseModel):
    """Result of checking URLs against robots.txt rules."""

    sitemap_url: str
    url: str
    matching_rule: str = ""
    status: str  # "Blocked" or "Not Blocked"


class TechStackResult(BaseModel):
    """Detected technologies for a website."""

    domain: str
    technologies: list[str]


class SslCertificateInfo(BaseModel):
    """TLS/SSL certificate information for a domain."""

    domain: str
    issuer: dict[str, str] = {}
    subject: dict[str, str] = {}
    valid_from: str = ""
    valid_to: str = ""
    serial_number: str = ""
    version: int | None = None
    subject_alt_names: list[str] = []
    error: str | None = None


class SecurityHeadersResult(BaseModel):
    """HTTP security-relevant response headers for a domain."""

    domain: str
    url: str
    status_code: int | None = None
    headers: dict[str, str] = {}
    grade: str = ""  # A/B/C/D/F based on coverage
    missing: list[str] = []
    error: str | None = None
