"""
services/security.py
=====================
STAGE 3 of the six-stage blueprint: Security & Moderation Gates.

GATE 1 (pre-generation): input filtering, before we ever call the provider.
GATE 2 (post-generation): inspect what came back before it's allowed to
become the final displayed/downloadable asset.

This is a lightweight, honestly-scoped implementation: a keyword/pattern
blocklist for Gate 1, and pass-through of the provider's own moderation
signals (e.g. content_policy_violation, finish_reason=FILTER) for Gate 2.
It does NOT claim to be a full trained safety classifier — that would be
its own research project. Anything the provider itself rejects also
surfaces here as a Gate 2 rejection.
"""

import re
from dataclasses import dataclass
from typing import Optional

from utils.logging_utils import get_logger

logger = get_logger(__name__)

# Intentionally coarse — a real deployment would use a dedicated
# moderation model/API. This exists so Gate 1 is a genuine, real check
# rather than a no-op placeholder.
_BLOCKED_PATTERNS = [
    r"\bchild\s+sexual\b",
    r"\bcsam\b",
    r"\bhow to make a bomb\b",
    r"\bmake\s+a\s+bioweapon\b",
]
_COMPILED_BLOCKLIST = [re.compile(p, re.I) for p in _BLOCKED_PATTERNS]


@dataclass
class SecurityResult:
    passed: bool
    code: Optional[str] = None
    message: Optional[str] = None


def pre_generation_check(prompt: str, negative_prompt: Optional[str], request_id: str) -> SecurityResult:
    combined = f"{prompt} {negative_prompt or ''}"
    for pattern in _COMPILED_BLOCKLIST:
        if pattern.search(combined):
            logger.warning("[%s] Gate 1 rejected prompt (sentinel_block)", request_id)
            return SecurityResult(
                passed=False,
                code="sentinel_block",
                message="This request could not be processed because it did not pass input safety filtering.",
            )
    return SecurityResult(passed=True)


def post_generation_check(provider_error: Optional[str], request_id: str) -> SecurityResult:
    """
    `provider_error` is populated when the provider itself signals a
    moderation rejection (e.g. HuggingFaceProvider raising
    CONTENT_POLICY_VIOLATION, or a hypothetical future provider setting
    finish_reason=FILTER). If it's None, the generated asset passes Gate 2
    here — final acceptance still depends on integrity + QA stages.
    """
    if provider_error:
        logger.warning("[%s] Gate 2 rejected output (%s)", request_id, provider_error)
        return SecurityResult(
            passed=False,
            code="moderation_blocked",
            message="This generation could not be displayed because it did not pass the required safety checks.",
        )
    return SecurityResult(passed=True)
