"""Shared HTTP utilities used across core modules."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from urllib.parse import urlparse

import requests
from browserforge.headers import HeaderGenerator
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 15
RETRY_STATUS = (429, 500, 502, 503, 504)


def requests_retry_session(
    retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = RETRY_STATUS,
    session: requests.Session | None = None,
) -> requests.Session:
    """Create a requests session with automatic retry logic.

    Retries on connect/read failures and on 429/5xx responses with exponential
    backoff. Adds a randomized browser-like User-Agent.
    """
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset({"GET", "HEAD", "OPTIONS", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def generate_headers() -> dict[str, str]:
    """Generate randomized browser headers using browserforge."""
    generator = HeaderGenerator(
        browser=("chrome", "firefox", "safari", "edge"),
        os=("windows", "macos", "linux", "android", "ios"),
        device=("desktop", "mobile"),
        locale=("en-US", "en"),
        http_version=2,
    )
    return generator.generate()


class HostRateLimiter:
    """Simple per-host minimum-interval rate limiter.

    Not a token bucket - just enforces a minimum gap between requests to the
    same host across threads. Suitable for scraping Google/Bing where short
    bursts cause CAPTCHAs.
    """

    def __init__(self, min_interval: float = 0.0) -> None:
        self._min_interval = min_interval
        self._last: dict[str, float] = defaultdict(lambda: 0.0)
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._dict_lock = threading.Lock()

    def wait(self, url: str) -> None:
        """Block until enough time has passed since the last call for this host."""
        if self._min_interval <= 0:
            return
        host = urlparse(url).netloc or url
        with self._dict_lock:
            lock = self._locks[host]
        with lock:
            now = time.monotonic()
            elapsed = now - self._last[host]
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last[host] = time.monotonic()
