"""
utils/file_utils.py
====================
Filename sanitization + safe path resolution.

Prevents path traversal (../../etc/passwd style attacks) by:
1. Stripping any directory component from user/derived filenames.
2. Generating our own unique filenames rather than trusting external input.
3. Resolving the final path and verifying it is still inside the intended
   storage directory before any file I/O happens.
"""

import re
import uuid
from pathlib import Path

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def sanitize_filename(name: str) -> str:
    name = Path(name).name  # drop any path components entirely
    name = _SAFE_CHARS.sub("_", name)
    return name or "asset"


def unique_filename(prefix: str, extension: str = "png") -> str:
    token = uuid.uuid4().hex[:12]
    return sanitize_filename(f"{prefix}_{token}.{extension}")


def resolve_within(base_dir: Path, filename: str) -> Path:
    """
    Build `base_dir / filename` and guarantee the result cannot escape
    `base_dir`, regardless of what `filename` contains.
    """
    if not isinstance(filename, str):
        raise ValueError("Filename must be a string")

    if filename in ("", ".", "..") or "/" in filename or "\\" in filename or filename.startswith("~"):
        raise ValueError("Path traversal attempt blocked")

    normalized = Path(filename)
    if any(part in ("", ".", "..") for part in normalized.parts):
        raise ValueError("Path traversal attempt blocked")

    safe_name = sanitize_filename(filename)
    candidate = (base_dir / safe_name).resolve()
    base_resolved = base_dir.resolve()

    if base_resolved not in candidate.parents and candidate != base_resolved:
        raise ValueError("Path traversal attempt blocked")

    return candidate


def delete_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
