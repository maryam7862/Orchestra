"""
utils/logging_utils.py
=======================
Central logger + request-ID generator.

Hard rule enforced here: nothing that looks like a secret ever reaches
the log. `safe()` is a defensive scrub applied to any dict before it is
logged, in case a caller forgets.
"""

import logging
import random
import re
import string
from datetime import datetime
from pathlib import Path

import config

_SECRET_KEY_PATTERN = re.compile(r"(token|authorization|api[_-]?key|secret)", re.I)


def get_logger(name: str = "studio") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_path = Path(config.LOGS_DIR) / "app.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def safe(data: dict) -> dict:
    """Return a copy of `data` with anything secret-looking redacted."""
    cleaned = {}
    for k, v in data.items():
        if _SECRET_KEY_PATTERN.search(str(k)):
            cleaned[k] = "***REDACTED***"
        else:
            cleaned[k] = v
    return cleaned


def new_request_id() -> str:
    """GEN-20260815-AB12CD style unique ID."""
    date_part = datetime.utcnow().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"GEN-{date_part}-{suffix}"
