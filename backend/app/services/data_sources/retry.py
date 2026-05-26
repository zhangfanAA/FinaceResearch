"""Resilient HTTP request helpers with exponential backoff retry.

Uses the ``tenacity`` library to automatically retry failed HTTP requests
with exponential backoff, jitter, and configurable retry conditions.

Usage:
    from app.services.data_sources.retry import resilient_get, resilient_get_json

    # Simple GET with automatic retry
    resp = resilient_get("https://push2.eastmoney.com/api/qt/clist/get", params={...})

    # GET with JSON parsing
    data = resilient_get_json("https://push2.eastmoney.com/api/qt/clist/get", params={...})
"""

from __future__ import annotations

import logging
import random
from typing import Any

import requests
from http.client import RemoteDisconnected
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
_MAX_ATTEMPTS = 4          # Total attempts (1 initial + 3 retries)
_WAIT_MIN_SECONDS = 1.0    # Minimum wait between retries
_WAIT_MAX_SECONDS = 15.0   # Maximum wait between retries
_JITTER_SECONDS = 1.0      # Random jitter added to each wait

# Exception types that trigger a retry
_RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ProxyError,
    RemoteDisconnected,
)

# HTTP status codes that trigger a retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _log_retry(retry_state: RetryCallState) -> None:
    """Log each retry attempt with context."""
    attempt = retry_state.attempt_number
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    wait = retry_state.next_action.sleep if retry_state.next_action else 0
    if exc:
        logger.warning(
            "HTTP request retry attempt %d/%d after %.1fs wait: %s",
            attempt, _MAX_ATTEMPTS, wait, exc,
        )


# ---------------------------------------------------------------------------
# Browser-like headers (rotate to avoid fingerprinting)
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) "
        "Gecko/20100101 Firefox/127.0"
    ),
]


def _default_headers() -> dict[str, str]:
    """Return browser-like headers with a random User-Agent."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Referer": "https://quote.eastmoney.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


class RetryableHTTPStatusError(Exception):
    """Raised when an HTTP response has a retryable status code."""

    def __init__(self, response: requests.Response) -> None:
        self.response = response
        super().__init__(f"HTTP {response.status_code} for {response.url}")


def _should_retry_status(exc: BaseException) -> bool:
    """Return True if the exception is a retryable HTTP status error."""
    if isinstance(exc, RetryableHTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type((*_RETRYABLE_EXCEPTIONS, RetryableHTTPStatusError)),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential_jitter(initial=_WAIT_MIN_SECONDS, max=_WAIT_MAX_SECONDS, jitter=_JITTER_SECONDS),
    before_sleep=_log_retry,
    reraise=True,
)
def resilient_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    session: requests.Session | None = None,
) -> requests.Response:
    """GET request with exponential backoff retry.

    Retries on ConnectionError, Timeout, ProxyError, and HTTP 429/5xx.
    Always forces direct connection (no proxy).

    Args:
        url: Target URL.
        params: Query parameters.
        headers: Extra headers (merged with browser-like defaults).
        timeout: Request timeout in seconds.
        session: Optional pre-configured Session (trust_env should be False).

    Returns:
        Successful Response object.

    Raises:
        requests.exceptions.RequestException: After all retries exhausted.
        RetryableHTTPStatusError: If the final attempt still returns a
            retryable status code.
    """
    merged_headers = {**_default_headers(), **(headers or {})}
    s = session or requests.Session()
    s.trust_env = False  # Never read system proxy env vars

    resp = s.get(
        url,
        params=params,
        headers=merged_headers,
        proxies={"http": None, "https": None},
        timeout=timeout,
    )
    if resp.status_code in _RETRYABLE_STATUS_CODES:
        raise RetryableHTTPStatusError(resp)
    resp.raise_for_status()
    return resp


@retry(
    retry=retry_if_exception_type((*_RETRYABLE_EXCEPTIONS, RetryableHTTPStatusError)),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential_jitter(initial=_WAIT_MIN_SECONDS, max=_WAIT_MAX_SECONDS, jitter=_JITTER_SECONDS),
    before_sleep=_log_retry,
    reraise=True,
)
def resilient_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """GET request that returns parsed JSON with automatic retry.

    Same retry policy as ``resilient_get``.

    Returns:
        Parsed JSON as a dict.

    Raises:
        json.JSONDecodeError: If response body is not valid JSON.
        requests.exceptions.RequestException: After all retries exhausted.
    """
    resp = resilient_get(url, params=params, headers=headers, timeout=timeout, session=session)
    return resp.json()
