"""MCP tools for domain information gathering."""

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register domain analysis tools with the MCP server."""

    @mcp.tool()
    def get_ip_address(domain: str) -> dict:
        """Resolve a domain to its IP address.

        Args:
            domain: Domain name (e.g., "example.com").

        Returns:
            Dict with domain and ip fields.
        """
        from seo_bhishma.core.domain_insight import get_ip_address as _get_ip

        ip = _get_ip(domain)
        return {"domain": domain, "ip": ip}

    @mcp.tool()
    def get_dns_records(domain: str) -> dict:
        """Fetch DNS records (A, AAAA, MX, NS, TXT, CNAME) for a domain.

        Args:
            domain: Domain name (e.g., "example.com").

        Returns:
            Dict with record types as keys and lists of values.
        """
        from seo_bhishma.core.domain_insight import get_dns_records as _get_dns

        return _get_dns(domain).model_dump()

    @mcp.tool()
    def get_whois_info(domain: str) -> dict:
        """Fetch WHOIS registration information for a domain.

        Args:
            domain: Domain name (e.g., "example.com").

        Returns:
            Dict with WHOIS data fields.
        """
        from seo_bhishma.core.domain_insight import get_whois_info as _get_whois

        return _get_whois(domain).model_dump()

    @mcp.tool()
    def get_ip_details(ip: str) -> dict:
        """Get detailed IP information including ASN, geolocation, and organization.

        Args:
            ip: IP address (e.g., "93.184.216.34").

        Returns:
            Dict with ASN info, city, region, country, organization, etc.
        """
        from seo_bhishma.core.domain_insight import get_ip_details as _get_details

        return _get_details(ip).model_dump()

    @mcp.tool()
    def find_subdomains(domain: str, threads: int = 40) -> dict:
        """Discover subdomains for a given domain using sublist3r.

        Args:
            domain: Domain name (e.g., "example.com").
            threads: Number of threads for enumeration.

        Returns:
            Dict with domain and list of discovered subdomains.
        """
        from seo_bhishma.core.domain_insight import find_subdomains as _find

        subdomains = _find(domain, threads=threads)
        return {"domain": domain, "subdomains": subdomains}

    @mcp.tool()
    def tech_stack_analysis(domain: str) -> dict:
        """Detect technologies used by a website (CMS, frameworks, analytics, etc.).

        Args:
            domain: Domain name (e.g., "example.com").

        Returns:
            Dict with domain and list of detected technologies.
        """
        from seo_bhishma.core.domain_insight import tech_analysis

        return tech_analysis(domain).model_dump()

    @mcp.tool()
    def fetch_robots_txt(domain: str) -> dict:
        """Fetch and parse robots.txt for a domain.

        Args:
            domain: Domain name (e.g., "example.com").

        Returns:
            Dict with raw_content, disallow_rules, and sitemaps.
        """
        from seo_bhishma.core.domain_insight import fetch_robots_txt as _fetch

        result = _fetch(domain)
        if result is None:
            return {"error": "robots.txt not found", "raw_content": "", "disallow_rules": [], "sitemaps": []}
        return result.model_dump()

    @mcp.tool()
    def check_urls_against_robots(
        domain: str,
        urls: list[str],
    ) -> dict:
        """Check URLs against a domain's robots.txt disallow rules.

        Args:
            domain: Domain name to fetch robots.txt from.
            urls: List of full URLs to check.

        Returns:
            Dict with results list and blocked_count.
        """
        from seo_bhishma.core.domain_insight import (
            check_urls_against_robots as _check,
            fetch_robots_txt as _fetch,
        )

        robots = _fetch(domain)
        if robots is None:
            return {"error": "robots.txt not found", "results": [], "blocked_count": 0}

        url_tuples = [(domain, url) for url in urls]
        results = _check(robots.disallow_rules, url_tuples)
        blocked = sum(1 for r in results if r.status == "Blocked")
        return {
            "results": [r.model_dump() for r in results],
            "blocked_count": blocked,
        }

    @mcp.tool()
    def validate_domain(input_string: str) -> dict:
        """Validate whether a string is a valid domain name or URL.

        Args:
            input_string: Domain name or URL to validate.

        Returns:
            Dict with input and is_valid boolean.
        """
        from seo_bhishma.core.domain_insight import is_valid_domain_or_url

        return {"input": input_string, "is_valid": is_valid_domain_or_url(input_string)}

    @mcp.tool()
    def parse_robots_txt(content: str) -> dict:
        """Parse a raw robots.txt string into disallow rules and sitemap URLs.

        Args:
            content: Raw robots.txt text.

        Returns:
            Dict with disallow_rules and sitemaps lists.
        """
        from seo_bhishma.core.domain_insight import parse_robots_txt as _parse

        disallows, sitemaps = _parse(content)
        return {"disallow_rules": disallows, "sitemaps": sitemaps}

    @mcp.tool()
    def reverse_ip_lookup(ip: str) -> dict:
        """Perform a reverse IP lookup (which domains are hosted on this IP).

        Uses Playwright to scrape domains.tntcode.com - requires a Playwright
        browser install.

        Args:
            ip: IP address.

        Returns:
            Dict with title, table_info, and domains list (or error).
        """
        import asyncio

        from seo_bhishma.core.domain_insight import reverse_ip_lookup_playwright

        try:
            result = asyncio.run(reverse_ip_lookup_playwright(ip))
        except RuntimeError:
            # Already inside an event loop (e.g. nested agent call)
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(reverse_ip_lookup_playwright(ip))
            finally:
                loop.close()

        if result is None:
            return {"error": "Reverse IP lookup failed or returned no data", "domains": []}
        return result.model_dump()

    @mcp.tool()
    def get_ssl_certificate(domain: str, port: int = 443) -> dict:
        """Fetch and parse the TLS certificate for a domain.

        Args:
            domain: Bare domain name.
            port: TLS port (default 443).

        Returns:
            Dict with issuer, subject, validity dates, serial, and SANs.
        """
        from seo_bhishma.core.domain_insight import get_ssl_certificate as _get_cert

        return _get_cert(domain, port=port).model_dump()

    @mcp.tool()
    def get_security_headers(domain: str) -> dict:
        """Audit a domain's HTTP security response headers.

        Checks HSTS, CSP, X-Frame-Options, X-Content-Type-Options,
        Referrer-Policy, Permissions-Policy, and X-XSS-Protection. Returns
        a letter grade based on coverage.

        Args:
            domain: Domain name.

        Returns:
            Dict with headers present, missing headers list, and grade.
        """
        from seo_bhishma.core.domain_insight import get_security_headers as _get_sec

        return _get_sec(domain).model_dump()
