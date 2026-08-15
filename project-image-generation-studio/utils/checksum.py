"""
utils/checksum.py
==================
SHA-256 of a file, computed in chunks so we never load a huge file into
memory just to hash it (same memory-safety principle as the streaming
downloader).
"""

import hashlib
from pathlib import Path

import config


def sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(config.STREAM_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
