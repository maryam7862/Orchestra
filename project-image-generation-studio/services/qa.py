"""
services/qa.py
===============
STAGE 6 of the six-stage blueprint: Automated Quality Assurance.

Combines the two QA lenses (aesthetic_qa.py, semantic_qa.py) into one
accept/reject decision.
"""

from dataclasses import dataclass
from pathlib import Path

from services import aesthetic_qa, semantic_qa


@dataclass
class QAResult:
    passed: bool
    aesthetic: aesthetic_qa.AestheticResult
    semantic: semantic_qa.SemanticResult
    reason: str | None = None


def run_qa(path: Path, prompt: str, request_id: str) -> QAResult:
    aesthetic_result = aesthetic_qa.evaluate(path, request_id)
    semantic_result = semantic_qa.evaluate(path, prompt, request_id)

    if not aesthetic_result.passed:
        return QAResult(
            passed=False, aesthetic=aesthetic_result, semantic=semantic_result,
            reason=f"Aesthetic score {aesthetic_result.score}/10 did not exceed threshold {aesthetic_result.threshold}.",
        )

    if not semantic_result.passed:
        return QAResult(
            passed=False, aesthetic=aesthetic_result, semantic=semantic_result,
            reason=f"Semantic alignment score {semantic_result.score}/10 was below threshold {semantic_result.threshold}.",
        )

    return QAResult(passed=True, aesthetic=aesthetic_result, semantic=semantic_result)
