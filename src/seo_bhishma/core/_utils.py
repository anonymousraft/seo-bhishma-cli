"""Shared utility functions used across core modules."""

from urllib.parse import urlparse


def extract_domain(url: str) -> str | None:
    """Extract the domain from a URL, stripping 'www.' prefix.

    Args:
        url: A URL string (with or without scheme).

    Returns:
        The domain string, or None if extraction fails.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc if parsed.netloc else parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return None
