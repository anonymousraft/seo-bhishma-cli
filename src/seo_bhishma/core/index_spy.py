"""Core bulk indexing status checker. No CLI dependencies."""

import asyncio
import logging
import time
from itertools import cycle

import requests
from bs4 import BeautifulSoup

from seo_bhishma.core._http import generate_headers
from seo_bhishma.models.common import ProgressCallback
from seo_bhishma.models.index_spy import (
    BatchIndexCheckResult,
    CaptchaConfig,
    CaptchaHandling,
    CheckMethod,
    IndexCheckResult,
    ProxyConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Proxy management
# ---------------------------------------------------------------------------


class ProxyRotator:
    """Manages a rotating pool of proxies with validation."""

    def __init__(self, proxies: list[str], mode: list[str] | None = None):
        self._proxies = proxies
        self._mode = mode or ["http", "https"]
        self._cycle = cycle(proxies)
        self._current: dict | None = None

    def next(self) -> str:
        """Get the next proxy from the pool."""
        return next(self._cycle)

    @property
    def mode(self) -> list[str]:
        return self._mode

    @property
    def current(self) -> dict | None:
        return self._current

    @current.setter
    def current(self, value: dict | None):
        self._current = value

    def validate_htmlsession(self, proxy: str, url: str = "https://www.google.com/") -> dict | None:
        """Validate a proxy using requests/HTMLSession.

        Args:
            proxy: Proxy address (host:port).
            url: URL to test against.

        Returns:
            Proxy dict if valid, None otherwise.
        """
        from requests_html import HTMLSession

        headers = generate_headers()

        for protocol in self._mode:
            proxies = {protocol: f"{protocol}://{proxy}"}
            session = HTMLSession()
            try:
                response = session.get(url, headers=headers, proxies=proxies, timeout=10)
                response.html.render(timeout=20)
                if response.status_code == 200 and "captcha" not in response.text.lower():
                    logger.info("Valid proxy: %s", proxy)
                    return proxies
                elif response.status_code == 429:
                    logger.warning("Proxy %s returned 429. Applying delay.", proxy)
                    time.sleep(60)
            except requests.RequestException as e:
                logger.debug("Proxy %s failed: %s", proxy, e)
            finally:
                session.close()

        return None

    async def validate_playwright(self, proxy: str, url: str = "https://www.google.com/") -> dict | None:
        """Validate a proxy using Playwright.

        Args:
            proxy: Proxy address (host:port).
            url: URL to test against.

        Returns:
            Proxy dict if valid, None otherwise.
        """
        from playwright.async_api import async_playwright

        for protocol in self._mode:
            proxy_server = f"{protocol}://{proxy}"
            for attempt in range(3):
                browser = None
                try:
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(
                            proxy={"server": proxy_server}
                        )
                        context = await browser.new_context()
                        page = await context.new_page()
                        await page.goto(url, timeout=60000)
                        content = await page.content()

                        if "captcha" not in content.lower():
                            logger.info("Valid proxy: %s (attempt %d)", proxy, attempt + 1)
                            await browser.close()
                            return {protocol: proxy_server}
                        else:
                            await browser.close()
                            break
                except Exception as e:
                    logger.debug("Proxy %s attempt %d failed: %s", proxy, attempt + 1, e)
                    if "ERR_TUNNEL_CONNECTION_FAILED" in str(e) or "ERR_PROXY_CONNECTION_FAILED" in str(e):
                        continue
                    break
                finally:
                    if browser:
                        try:
                            await browser.close()
                        except Exception:
                            pass

        return None

    def find_valid(self, method: CheckMethod, max_attempts: int = 0) -> dict | None:
        """Find a valid proxy by cycling through the pool.

        Args:
            method: Check method to use for validation.
            max_attempts: Max proxies to try (0 = try all once).

        Returns:
            Valid proxy dict, or None.
        """
        attempts = max_attempts or len(self._proxies)
        for _ in range(attempts):
            proxy = self.next()
            if method == CheckMethod.HTML_SESSION:
                result = self.validate_htmlsession(proxy)
            else:
                result = _run_async(self.validate_playwright(proxy))
            if result:
                self._current = result
                return result
        return None


def _run_async(coro):
    """Run an async coroutine, even if a loop is already running.

    Falls back to ``asyncio.new_event_loop()`` when called from inside an
    existing loop (e.g. agents, notebooks).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Running loop exists; spawn a fresh loop in a worker thread
    import threading

    result_box: dict = {}

    def runner():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            result_box["value"] = new_loop.run_until_complete(coro)
        except Exception as exc:
            result_box["error"] = exc
        finally:
            new_loop.close()

    t = threading.Thread(target=runner)
    t.start()
    t.join()
    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("value")


# ---------------------------------------------------------------------------
# CAPTCHA solving
# ---------------------------------------------------------------------------


def get_site_key(url: str) -> str | None:
    """Extract reCAPTCHA site key from a page.

    Args:
        url: Page URL to scan.

    Returns:
        Site key string, or None if not found.
    """
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        tag = soup.find("div", {"class": "g-recaptcha"})
        if tag and "data-sitekey" in tag.attrs:
            return tag["data-sitekey"]
    except Exception as e:
        logger.error("Error getting site key: %s", e)
    return None


def solve_captcha_2captcha(api_key: str, page_url: str, site_key: str) -> str | None:
    """Solve reCAPTCHA using 2Captcha service.

    Args:
        api_key: 2Captcha API key.
        page_url: Page where CAPTCHA appears.
        site_key: reCAPTCHA site key.

    Returns:
        CAPTCHA solution token, or None on failure.
    """
    try:
        payload = {
            "key": api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
        }
        response = requests.post("http://2captcha.com/in.php", data=payload, timeout=30)
        parts = response.text.split("|")
        if parts[0] != "OK":
            logger.error("2Captcha error: %s", response.text)
            return None

        request_id = parts[1]
        solution_params = {"key": api_key, "action": "get", "id": request_id}

        for _ in range(60):  # Max 5 minutes
            time.sleep(5)
            result = requests.get(
                "http://2captcha.com/res.php", params=solution_params, timeout=30
            )
            result_parts = result.text.split("|")
            if result_parts[0] == "OK":
                return result_parts[1]
            if result_parts[0] != "CAPCHA_NOT_READY":
                logger.error("2Captcha solve error: %s", result.text)
                return None

    except Exception as e:
        logger.error("Error solving captcha via 2Captcha: %s", e)
    return None


def solve_captcha_anticaptcha(api_key: str, page_url: str, site_key: str) -> str | None:
    """Solve reCAPTCHA using Anti-Captcha service.

    Args:
        api_key: Anti-Captcha API key.
        page_url: Page where CAPTCHA appears.
        site_key: reCAPTCHA site key.

    Returns:
        CAPTCHA solution token, or None on failure.
    """
    try:
        task_payload = {
            "clientKey": api_key,
            "task": {
                "type": "NoCaptchaTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
        }
        response = requests.post(
            "https://api.anti-captcha.com/createTask", json=task_payload, timeout=30
        )
        data = response.json()
        if data.get("errorId") != 0:
            logger.error("Anti-Captcha error: %s", data.get("errorDescription"))
            return None

        task_id = data["taskId"]
        result_payload = {"clientKey": api_key, "taskId": task_id}

        for _ in range(60):
            time.sleep(5)
            result = requests.post(
                "https://api.anti-captcha.com/getTaskResult",
                json=result_payload,
                timeout=30,
            )
            result_data = result.json()
            if result_data["status"] == "ready":
                return result_data["solution"]["gRecaptchaResponse"]
            if result_data["status"] != "processing":
                logger.error("Anti-Captcha solve error: %s", result_data.get("errorDescription"))
                return None

    except Exception as e:
        logger.error("Error solving captcha via Anti-Captcha: %s", e)
    return None


def solve_captcha(
    captcha_config: CaptchaConfig, page_url: str, site_key: str
) -> str | None:
    """Solve a CAPTCHA using the configured service.

    Args:
        captcha_config: CAPTCHA service configuration.
        page_url: Page URL where CAPTCHA appears.
        site_key: reCAPTCHA site key.

    Returns:
        Solution token, or None.
    """
    if captcha_config.service.lower() == "2captcha":
        return solve_captcha_2captcha(captcha_config.api_key, page_url, site_key)
    elif captcha_config.service.lower() == "anti-captcha":
        return solve_captcha_anticaptcha(captcha_config.api_key, page_url, site_key)
    logger.error("Unknown captcha service: %s", captcha_config.service)
    return None


# ---------------------------------------------------------------------------
# Indexing status checks
# ---------------------------------------------------------------------------


def _parse_indexing_html(html_content: str, url: str) -> str:
    """Parse Google search results HTML to determine indexing status.

    Args:
        html_content: HTML page content.
        url: URL being checked.

    Returns:
        "Indexed", "Not Indexed", or "Captcha Encountered".
    """
    lower = html_content.lower()
    if "captcha" in lower or "unusual traffic" in lower or "/sorry/index" in lower:
        return "Captcha Encountered"

    soup = BeautifulSoup(html_content, "html.parser")

    # Multiple Google "no results" indicators (DOM changes over time)
    no_results_markers = [
        "did not match any documents",
        "no information is available",
        "your search -",  # "Your search - <url> - did not match..."
    ]
    page_text = soup.get_text(" ", strip=True).lower()
    if any(marker in page_text for marker in no_results_markers):
        return "Not Indexed"

    # Multiple selector fallbacks - Google changes class names frequently
    selectors = ["div.g", "div.tF2Cxc", "div[data-hveid]", "div.MjjYud"]
    for selector in selectors:
        for result in soup.select(selector):
            link = result.find("a", href=True)
            if link and url in link["href"]:
                return "Indexed"

    # Final fallback: any anchor whose href references the URL
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if url in href and href.startswith(("http://", "https://", "/url?")):
            return "Indexed"

    return "Not Indexed"


def check_indexing_htmlsession(
    url: str,
    proxies: dict | None = None,
    captcha_config: CaptchaConfig | None = None,
    rate_limit: float = 0,
) -> str:
    """Check URL indexing status using HTMLSession.

    Args:
        url: URL to check.
        proxies: Optional proxy dict.
        captcha_config: Optional CAPTCHA solving configuration.
        rate_limit: Delay after request.

    Returns:
        Status string: "Indexed", "Not Indexed", "Captcha Encountered", or "Error: ...".
    """
    from requests_html import HTMLSession

    session = HTMLSession()
    search_url = f"https://www.google.com/search?q=site:{url}"
    headers = generate_headers()

    try:
        response = session.get(search_url, headers=headers, proxies=proxies, timeout=10)
        response.html.render(timeout=20)

        if "captcha" in response.text.lower() and captcha_config:
            site_key = get_site_key(search_url)
            if site_key:
                solution = solve_captcha(captcha_config, search_url, site_key)
                if solution:
                    headers["g-recaptcha-response"] = solution
                    response = session.get(
                        search_url, headers=headers, proxies=proxies, timeout=10
                    )
                    response.html.render(timeout=20)

        return _parse_indexing_html(response.html.html, url)

    except Exception as e:
        logger.error("Error checking indexing for %s: %s", url, e)
        return f"Error: {e}"
    finally:
        session.close()
        if rate_limit > 0:
            time.sleep(rate_limit)


async def check_indexing_playwright(
    url: str,
    proxy: dict | None = None,
    captcha_handling: CaptchaHandling = CaptchaHandling.AUTOMATIC,
    headless: bool = False,
) -> str:
    """Check URL indexing status using Playwright.

    Args:
        url: URL to check.
        proxy: Optional proxy dict.
        captcha_handling: How to handle CAPTCHAs.
        headless: Whether to run browser in headless mode.

    Returns:
        Status string.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser_options: dict = {
            "headless": headless,
            "args": [
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--log-level=3",
            ],
        }

        if proxy:
            server = proxy.get("http") or proxy.get("https", "")
            browser_options["proxy"] = {"server": server}

        browser = await p.chromium.launch(**browser_options)
        page = await browser.new_page()

        try:
            search_url = f"https://www.google.com/search?q=site:{url}"
            await page.goto(search_url)
            await page.wait_for_timeout(5000)

            content = await page.content()

            if "captcha" in content.lower():
                if not headless and captcha_handling == CaptchaHandling.BY_USER:
                    logger.info("CAPTCHA detected. Waiting for user to solve...")
                    for _ in range(120):  # Wait up to 10 minutes
                        await page.wait_for_timeout(5000)
                        content = await page.content()
                        if "captcha" not in content.lower():
                            break
                    else:
                        await browser.close()
                        return "Captcha Encountered"
                else:
                    await browser.close()
                    return "Captcha Encountered"

            return _parse_indexing_html(content, url)

        except Exception as e:
            if "ERR_TUNNEL_CONNECTION_FAILED" in str(e):
                return "Proxy Error"
            logger.error("Playwright error checking %s: %s", url, e)
            return f"Error: {e}"
        finally:
            await browser.close()


def check_indexing_status(
    url: str,
    method: CheckMethod = CheckMethod.HTML_SESSION,
    proxy: dict | None = None,
    captcha_config: CaptchaConfig | None = None,
    captcha_handling: CaptchaHandling = CaptchaHandling.AUTOMATIC,
    headless: bool = False,
    rate_limit: float = 0,
) -> IndexCheckResult:
    """Check indexing status for a single URL.

    Args:
        url: URL to check.
        method: Check method to use.
        proxy: Optional proxy dict.
        captcha_config: Optional CAPTCHA configuration.
        captcha_handling: How to handle CAPTCHAs (Playwright only).
        headless: Headless mode (Playwright only).
        rate_limit: Delay after check.

    Returns:
        IndexCheckResult.
    """
    proxy_str = str(proxy) if proxy else "No Proxy"

    if method == CheckMethod.HTML_SESSION:
        status = check_indexing_htmlsession(url, proxy, captcha_config, rate_limit)
    else:
        status = asyncio.run(
            check_indexing_playwright(url, proxy, captcha_handling, headless)
        )

    return IndexCheckResult(url=url, status=status, proxy_used=proxy_str)


def batch_check_indexing(
    urls: list[str],
    method: CheckMethod = CheckMethod.HTML_SESSION,
    proxy_config: ProxyConfig | None = None,
    captcha_config: CaptchaConfig | None = None,
    captcha_handling: CaptchaHandling = CaptchaHandling.AUTOMATIC,
    headless: bool = False,
    rate_limit: float = 0,
    max_captcha_retries: int = 3,
    on_progress: ProgressCallback | None = None,
) -> BatchIndexCheckResult:
    """Check indexing status for multiple URLs with proxy rotation and CAPTCHA handling.

    Args:
        urls: List of URLs to check.
        method: Check method.
        proxy_config: Optional proxy configuration.
        captcha_config: Optional CAPTCHA configuration.
        captcha_handling: CAPTCHA handling strategy.
        headless: Headless mode.
        rate_limit: Delay between checks.
        max_captcha_retries: Max consecutive CAPTCHA failures before stopping.
        on_progress: Optional progress callback.

    Returns:
        BatchIndexCheckResult with all results.
    """
    results: list[IndexCheckResult] = []
    rotator = ProxyRotator(proxy_config.proxy_list, proxy_config.mode) if proxy_config else None
    captcha_failures = 0

    # Find initial valid proxy
    if rotator:
        valid = rotator.find_valid(method)
        if not valid:
            logger.warning("No valid proxies found. Proceeding without proxy.")
            rotator = None

    for i, url in enumerate(urls):
        proxy = rotator.current if rotator else None

        result = check_indexing_status(
            url, method, proxy, captcha_config, captcha_handling, headless, rate_limit
        )

        # Handle CAPTCHA failures with proxy rotation
        if "Captcha" in result.status and rotator:
            captcha_failures += 1
            new_proxy = rotator.find_valid(method)
            if new_proxy:
                result = check_indexing_status(
                    url, method, new_proxy, captcha_config, captcha_handling, headless, rate_limit
                )
                if "Captcha" not in result.status:
                    captcha_failures = 0

        elif "Captcha" in result.status:
            captcha_failures += 1

        if "Captcha" not in result.status and "Proxy Error" not in result.status:
            results.append(result)
            captcha_failures = 0
        elif "Proxy Error" in result.status and rotator:
            new_proxy = rotator.find_valid(method)
            if new_proxy:
                result = check_indexing_status(
                    url, method, new_proxy, captcha_config, captcha_handling, headless, rate_limit
                )
                if "Captcha" not in result.status and "Proxy Error" not in result.status:
                    results.append(result)

        if captcha_failures >= max_captcha_retries:
            logger.error("Too many CAPTCHA failures (%d). Stopping.", captcha_failures)
            break

        if on_progress:
            on_progress(i + 1, len(urls))

    indexed = sum(1 for r in results if r.status == "Indexed")
    not_indexed = sum(1 for r in results if r.status == "Not Indexed")
    errors = sum(1 for r in results if r.status.startswith("Error"))

    return BatchIndexCheckResult(
        results=results,
        total_checked=len(results),
        total_indexed=indexed,
        total_not_indexed=not_indexed,
        total_errors=errors,
    )
