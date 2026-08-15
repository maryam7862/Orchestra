"""
services/retry.py
==================
Bounded exponential-backoff-with-jitter retry helper.

Retries ONLY on:
  - connection timeout
  - read timeout
  - HTTP 429 (Too Many Requests)
  - HTTP 503 (Service Unavailable)

Never retries on:
  - invalid API key / auth failure
  - invalid request / invalid prompt / unsupported parameter
  - security rejection

Callers report status via callback so the pipeline UI can show
PROCESSING / RETRYING / SUCCESS / FAILED accurately (no fake statuses).
"""

import random
import time
from typing import Callable, Optional

import config
from utils.logging_utils import get_logger

logger = get_logger(__name__)


class NonRetryableError(Exception):
    """Raised by a wrapped call to signal 'do not retry this'."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RetryableError(Exception):
    """Raised by a wrapped call to signal 'this is safe to retry'."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _compute_delay(attempt: int) -> float:
    base = min(config.RETRY_BASE_DELAY * (2 ** (attempt - 1)), config.RETRY_MAX_DELAY)
    jitter_range = base * config.RETRY_JITTER
    return max(0.0, base + random.uniform(-jitter_range, jitter_range))


def run_with_retry(
    func: Callable[[], object],
    request_id: str,
    on_status: Optional[Callable[[str, dict], None]] = None,
):
    """
    Calls `func()`. If it raises RetryableError, retries with exponential
    backoff + jitter up to config.MAX_RETRY_ATTEMPTS. If it raises
    NonRetryableError, fails immediately (fail fast).

    `on_status(stage_status, detail)` is called with values like
    "PROCESSING", "RETRYING", "SUCCESS", "FAILED" so the frontend pipeline
    monitor reflects real backend state.
    """
    last_error = None

    for attempt in range(1, config.MAX_RETRY_ATTEMPTS + 1):
        try:
            if on_status:
                on_status("PROCESSING", {"attempt": attempt})
            result = func()
            if on_status:
                on_status("SUCCESS", {"attempt": attempt})
            return result

        except NonRetryableError as exc:
            logger.warning(
                "[%s] non-retryable error on attempt %d: %s - %s",
                request_id, attempt, exc.code, exc.message,
            )
            if on_status:
                on_status("FAILED", {"code": exc.code, "message": exc.message})
            raise

        except RetryableError as exc:
            last_error = exc
            logger.warning(
                "[%s] retryable error on attempt %d/%d: %s - %s",
                request_id, attempt, config.MAX_RETRY_ATTEMPTS, exc.code, exc.message,
            )
            if attempt >= config.MAX_RETRY_ATTEMPTS:
                break
            delay = _compute_delay(attempt)
            if on_status:
                on_status("RETRYING", {
                    "attempt": attempt,
                    "next_attempt_in_seconds": round(delay, 2),
                    "code": exc.code,
                })
            time.sleep(delay)

    if on_status:
        on_status("FAILED", {
            "code": getattr(last_error, "code", "MAX_RETRIES_EXCEEDED"),
            "message": getattr(last_error, "message", "Maximum retry attempts exceeded."),
        })
    raise last_error or RetryableError("MAX_RETRIES_EXCEEDED", "Maximum retry attempts exceeded.")
