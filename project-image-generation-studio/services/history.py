"""
services/history.py
====================
Simple JSON-file-backed generation history. Deliberately not a database —
this is a single-user local studio app — but isolated behind functions so
it could be swapped for SQLite later without touching callers.
"""

import json
import threading
from pathlib import Path

import config

_lock = threading.Lock()


def _load() -> list:
    if not config.HISTORY_FILE.exists():
        return []
    try:
        return json.loads(config.HISTORY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: list) -> None:
    config.HISTORY_FILE.write_text(json.dumps(items, indent=2))


def add_entry(entry: dict) -> None:
    with _lock:
        items = _load()
        items.insert(0, entry)
        items = items[:200]  # cap history length
        _save(items)


def get_history(limit: int = 50) -> list:
    with _lock:
        return _load()[:limit]
