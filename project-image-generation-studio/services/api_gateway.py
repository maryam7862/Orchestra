"""
services/api_gateway.py
========================
STAGE 2 of the six-stage blueprint: Network API Gateway.

Centralizes:
  - explicit split timeouts (connection=3.05s, read=60s) — Python's
    `requests` has NO default timeout, so every call MUST set one
  - classification of exceptions into Retryable vs NonRetryable
  - status-code handling (429/503 retryable, 4xx auth/validation not)
  - memory-safe streaming downloads (64KiB chunks)

Both the Hugging Face SDK path and any raw HTTP fallback go through here
so HTTP handling isn't scattered across the codebase.
"""

from pathlib import Path

import requests

import config
from services.retry import RetryableError, NonRetryableError
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def classify_and_raise(exc: Exception, context: str):
    """
    Turn a low-level exception into RetryableError or NonRetryableError so
    services/retry.py can act on it correctly.
    """
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        raise RetryableError("CONNECT_TIMEOUT", f"{context}: could not establish connection in time.") from exc

    if isinstance(exc, requests.exceptions.ReadTimeout):
        raise RetryableError("READ_TIMEOUT", f"{context}: server accepted the connection but took too long to respond.") from exc

    if isinstance(exc, requests.exceptions.ConnectionError):
        raise RetryableError("CONNECTION_ERROR", f"{context}: network/connection error.") from exc

    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", None)
        if status in config.RETRYABLE_STATUS_CODES:
            raise RetryableError(f"HTTP_{status}", f"{context}: received retryable status {status}.") from exc
        raise NonRetryableError(f"HTTP_{status}", f"{context}: request failed with status {status}.") from exc

    # Unknown errors are treated as non-retryable by default (fail fast,
    # don't hammer a broken integration).
    raise NonRetryableError("UNKNOWN_ERROR", f"{context}: {exc}") from exc


def stream_download_to_file(url: str, destination: Path, request_id: str) -> Path:
    """
    Memory-safe download of a remote image URL.

    Never uses response.content on a large binary. Streams in
    config.STREAM_CHUNK_SIZE (64KiB) chunks straight to disk.
    """
    try:
        with requests.get(url, stream=True, timeout=config.REQUEST_TIMEOUT) as response:
            response.raise_for_status()
            bytes_written = 0
            with open(destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=config.STREAM_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)

            if bytes_written == 0:
                destination.unlink(missing_ok=True)
                raise NonRetryableError("EMPTY_RESPONSE", "Downloaded file was empty.")

            logger.info("[%s] streamed %d bytes to %s", request_id, bytes_written, destination.name)
            return destination

    except (RetryableError, NonRetryableError):
        raise
    except requests.exceptions.RequestException as exc:
        destination.unlink(missing_ok=True)
        classify_and_raise(exc, "stream_download")
