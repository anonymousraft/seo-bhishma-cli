"""Domain exception hierarchy for seo_bhishma core modules."""


class SeoBhishmaError(Exception):
    """Base error for all seo-bhishma operations."""


class NetworkError(SeoBhishmaError):
    """Raised when an outbound HTTP/DNS request fails."""


class ParseError(SeoBhishmaError):
    """Raised when a response payload cannot be parsed (XML, HTML, CSV, JSON)."""


class AuthError(SeoBhishmaError):
    """Raised when authentication or authorization fails (GSC OAuth, API keys)."""


class RateLimitError(NetworkError):
    """Raised when a remote endpoint returns 429 or signals rate limiting."""


class CaptchaError(SeoBhishmaError):
    """Raised when a CAPTCHA challenge is encountered and cannot be solved."""


class ConfigError(SeoBhishmaError):
    """Raised when required configuration is missing or invalid."""
