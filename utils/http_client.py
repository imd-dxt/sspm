"""
Reusable HTTP client with retry, rate limiting, and structured logging.
"""
import time
import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

log = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on network errors and 5xx / 429 responses."""
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        return code in (429, 500, 502, 503, 504)
    return False


class TokenBucket:
    """Thread-safe token bucket for rate limiting."""

    def __init__(self, rate: float):
        """
        Args:
            rate: maximum requests per second
        """
        self._rate = rate
        self._tokens = rate
        self._last = time.monotonic()

    def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            sleep_for = (1 - self._tokens) / self._rate
            time.sleep(sleep_for)


class RateLimitedSession:
    """
    Wraps requests.Session with:
      - per-second rate limiting (token bucket)
      - automatic retry with exponential backoff
      - request/response logging
      - configurable timeout
    """

    def __init__(
        self,
        rate_limit_rps: float = 5.0,
        max_retries: int = 3,
        timeout: int = 30,
        base_url: str = "",
    ):
        self._bucket = TokenBucket(rate_limit_rps)
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")

        self._session = requests.Session()
        adapter = HTTPAdapter(max_retries=0)  # tenacity handles retries
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        self._max_retries = max_retries

    def update_headers(self, headers: dict[str, str]) -> None:
        self._session.headers.update(headers)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self._base_url}{path}" if path.startswith("/") else path

        @retry(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=60),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        )
        def _do() -> requests.Response:
            self._bucket.acquire()
            log.debug("http_request", extra={"method": method, "url": url})
            resp = self._session.request(
                method,
                url,
                params=params,
                json=json,
                timeout=self._timeout,
                **kwargs,
            )
            # Honour Retry-After header on 429
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                log.warning("rate_limited", extra={"retry_after": retry_after, "url": url})
                time.sleep(retry_after)
                resp.raise_for_status()
            resp.raise_for_status()
            return resp

        return _do()

    def get(self, path: str, params: Optional[dict] = None, **kw: Any) -> Any:
        return self._request("GET", path, params=params, **kw).json()

    def get_response(self, path: str, params: Optional[dict] = None, **kw: Any) -> requests.Response:
        """Return the raw Response object (useful when you need headers)."""
        return self._request("GET", path, params=params, **kw)

    def post(self, path: str, json: Optional[dict] = None, **kw: Any) -> Any:
        return self._request("POST", path, json=json, **kw).json()

    def close(self) -> None:
        self._session.close()
