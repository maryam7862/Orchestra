"""
services/integrity.py
======================
STAGE 5 of the six-stage blueprint: Integrity Verification.

A file that passes Image.open() can still be a truncated PNG with
corrupted pixel data past a certain byte offset — headers/metadata are
read first and can look perfectly valid even if the data section is
incomplete. Image.open() is lazy; it does not decode pixel data.

Image.load() forces a full decode of every pixel. If the stream was
truncated or corrupted, THIS is where it throws (typically OSError),
not at open() time. That is why both calls are required, in this order.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from utils.checksum import sha256_of_file
from utils.file_utils import delete_if_exists
from utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class IntegrityResult:
    passed: bool
    width: Optional[int] = None
    height: Optional[int] = None
    image_format: Optional[str] = None
    byte_size: Optional[int] = None
    checksum: Optional[str] = None
    error: Optional[str] = None


def verify_and_fingerprint(path: Path, request_id: str) -> IntegrityResult:
    if not path.exists() or path.stat().st_size == 0:
        return IntegrityResult(passed=False, error="File missing or empty after save.")

    try:
        with Image.open(path) as image:
            image.load()  # forces full pixel decode; this is the real check
            width, height = image.width, image.height
            image_format = image.format
    except OSError as exc:
        logger.warning("[%s] integrity check FAILED (corrupted/truncated image): %s", request_id, exc)
        delete_if_exists(path)
        return IntegrityResult(passed=False, error="Generated image failed pixel-level decode (corrupted or truncated).")

    byte_size = path.stat().st_size
    checksum = sha256_of_file(path)

    logger.info(
        "[%s] integrity check passed: %dx%d %s, %d bytes, sha256=%s",
        request_id, width, height, image_format, byte_size, checksum[:12],
    )

    return IntegrityResult(
        passed=True,
        width=width,
        height=height,
        image_format=image_format,
        byte_size=byte_size,
        checksum=checksum,
    )
