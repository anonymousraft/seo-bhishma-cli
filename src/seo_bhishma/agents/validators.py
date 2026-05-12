"""Live API-key validators used by the first-run wizard and ``config set``.

Each validator makes one cheap real API call so the wizard can give the user
immediate, accurate feedback before persisting the key. Failures are
classified into a small enum so the wizard can branch (offer retry vs skip)
without parsing free-form error strings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """Result of a live key validation call."""

    OK = "ok"
    UNAUTHORIZED = "unauthorized"  # 401 / invalid key
    FORBIDDEN = "forbidden"  # 403 (e.g. region block or revoked)
    RATE_LIMITED = "rate_limited"  # 429
    NETWORK = "network"  # connect / read timeout
    UNKNOWN = "unknown"  # anything else


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a single ``validate_*_key()`` call."""

    status: ValidationStatus
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ValidationStatus.OK

    @property
    def retriable(self) -> bool:
        """True if the user might succeed by re-entering a different key."""
        return self.status in {
            ValidationStatus.UNAUTHORIZED,
            ValidationStatus.FORBIDDEN,
            ValidationStatus.UNKNOWN,
        }


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def validate_openai_key(api_key: str, timeout: float = 10.0) -> ValidationResult:
    """Validate an OpenAI key by listing the available models.

    No tokens are consumed by ``GET /v1/models``. Returns within ``timeout``
    seconds (or sooner) on network failures.
    """
    if not api_key.strip():
        return ValidationResult(ValidationStatus.UNAUTHORIZED, "empty key")

    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        return _classify_http(response.status_code, response.text)
    except Exception as e:  # noqa: BLE001  - httpx raises many types; group them
        logger.debug("OpenAI validation failed: %s", e)
        return ValidationResult(ValidationStatus.NETWORK, str(e))


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

# ``messages.create`` is the cheapest endpoint that exercises auth. With
# max_tokens=1 the cost is sub-cent. We use Haiku for the smallest possible bill.
_ANTHROPIC_VALIDATION_MODEL = "claude-haiku-4-5"


def validate_anthropic_key(api_key: str, timeout: float = 10.0) -> ValidationResult:
    """Validate an Anthropic key with a single-token Haiku completion.

    Cost: roughly one input token plus up to one output token (~$0.0001).
    """
    if not api_key.strip():
        return ValidationResult(ValidationStatus.UNAUTHORIZED, "empty key")

    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _ANTHROPIC_VALIDATION_MODEL,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        return _classify_http(response.status_code, response.text)
    except Exception as e:  # noqa: BLE001
        logger.debug("Anthropic validation failed: %s", e)
        return ValidationResult(ValidationStatus.NETWORK, str(e))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_http(status: int, body: str) -> ValidationResult:
    """Map an HTTP status code to a :class:`ValidationResult`."""
    if 200 <= status < 300:
        return ValidationResult(ValidationStatus.OK)
    if status == 401:
        return ValidationResult(ValidationStatus.UNAUTHORIZED, _short(body))
    if status == 403:
        return ValidationResult(ValidationStatus.FORBIDDEN, _short(body))
    if status == 429:
        return ValidationResult(ValidationStatus.RATE_LIMITED, _short(body))
    return ValidationResult(ValidationStatus.UNKNOWN, f"HTTP {status}: {_short(body)}")


def _short(text: str, limit: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"
