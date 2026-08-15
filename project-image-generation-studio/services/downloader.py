"""
services/downloader.py
=======================
STAGE 4 of the six-stage blueprint: Transport Protocol.

Handles turning whatever the provider gave us (a PIL.Image object, a
remote URL, or raw bytes) into a file on disk, using a memory-safe path
in each case:

  - pil_object  -> encoded and written directly (already fully decoded
                   in memory by the SDK; no remote streaming applies)
  - remote_url  -> services/api_gateway.stream_download_to_file (64KiB
                   chunks, never response.content)
  - raw_bytes   -> written in STREAM_CHUNK_SIZE-sized slices, never one
                   giant .write() call on an unbounded buffer

This file is honest about which path is actually taken (Project 3 slide
29's "do not pretend HTTP streaming occurred" requirement).
"""

from pathlib import Path

import config
from services.api_gateway import stream_download_to_file
from services.image_provider import ProviderResult
from services.retry import NonRetryableError
from utils.file_utils import unique_filename, resolve_within, delete_if_exists
from utils.logging_utils import get_logger

logger = get_logger(__name__)


def save_provider_result(result: ProviderResult, request_id: str) -> Path:
    filename = unique_filename(prefix=request_id, extension="png")
    destination = resolve_within(config.GENERATED_ASSETS_DIR, filename)

    if result.source_kind == "pil_object":
        try:
            result.pil_image.save(destination, format="PNG")
        except Exception as exc:  # noqa: BLE001
            delete_if_exists(destination)
            raise NonRetryableError("SAVE_FAILED", f"Could not save generated image: {exc}") from exc
        logger.info("[%s] saved PIL-object image directly (no remote streaming was applicable)", request_id)
        return destination

    if result.source_kind == "remote_url":
        return stream_download_to_file(result.remote_url, destination, request_id)

    if result.source_kind == "raw_bytes":
        try:
            data = result.raw_bytes
            with open(destination, "wb") as f:
                for i in range(0, len(data), config.STREAM_CHUNK_SIZE):
                    f.write(data[i:i + config.STREAM_CHUNK_SIZE])
        except OSError as exc:
            delete_if_exists(destination)
            raise NonRetryableError("SAVE_FAILED", f"Could not write image bytes: {exc}") from exc
        logger.info("[%s] wrote raw bytes to disk in %d-byte chunks", request_id, config.STREAM_CHUNK_SIZE)
        return destination

    raise NonRetryableError("UNKNOWN_SOURCE_KIND", f"Unhandled provider result kind: {result.source_kind}")
