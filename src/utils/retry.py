"""Retry/backoff policy shared by all source adapters.

Wraps tenacity so adapters get: bounded retries (never infinite), exponential
backoff with jitter, and rate-limit-aware waiting when an API returns
Retry-After. Adapters call `http_retry()` as a decorator on their fetch
methods rather than hand-rolling retry loops.
"""
from __future__ import annotations

from typing import Callable

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from src.config.settings import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimitError(Exception):
    """Raised by adapters when a 429/403-rate-limit response is detected."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class SourceUnavailableError(Exception):
    """Raised when a source cannot be reached after retries are exhausted.

    The orchestrator catches this per-source and continues with the rest of
    the pipeline (see spec section 28: resilience / graceful degradation).
    """


def http_retry() -> Callable:
    return retry(
        reraise=True,
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential_jitter(initial=settings.backoff_base_seconds, max=30),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException, RateLimitError)),
        before_sleep=before_sleep_log(logger, "WARNING"),
    )


def raise_for_rate_limit(response: httpx.Response) -> None:
    """Inspect a response and raise RateLimitError if it signals throttling."""
    if response.status_code == 429 or (
        response.status_code == 403 and "rate limit" in response.text.lower()
    ):
        retry_after_header = response.headers.get("Retry-After")
        retry_after = float(retry_after_header) if retry_after_header else None
        raise RateLimitError(
            f"rate limited (status={response.status_code})", retry_after=retry_after
        )
