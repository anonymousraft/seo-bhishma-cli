"""Models for bulk indexing checker (Index Spy)."""

from enum import Enum

from pydantic import BaseModel


class CheckMethod(str, Enum):
    """Supported methods for checking indexing status."""

    HTML_SESSION = "htmlsession"
    PLAYWRIGHT = "playwright"


class CaptchaHandling(str, Enum):
    """How to handle CAPTCHAs during indexing checks."""

    BY_USER = "by_user"
    AUTOMATIC = "automatic"


class ProxyConfig(BaseModel):
    """Proxy configuration for indexing checks."""

    proxy_list: list[str]
    mode: list[str] = ["http", "https"]


class CaptchaConfig(BaseModel):
    """CAPTCHA solving service configuration."""

    service: str  # "2captcha" or "anti-captcha"
    api_key: str


class IndexCheckResult(BaseModel):
    """Result of checking a single URL's indexing status."""

    url: str
    status: str  # "Indexed", "Not Indexed", "Captcha Encountered", "Error: ..."
    proxy_used: str = "No Proxy"


class BatchIndexCheckResult(BaseModel):
    """Result of checking multiple URLs' indexing status."""

    results: list[IndexCheckResult]
    total_checked: int
    total_indexed: int
    total_not_indexed: int
    total_errors: int
