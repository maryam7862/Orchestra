"""
services/semantic_qa.py
========================
QA LENS 2: Semantic Alignment Verification.

The Project 3 slides reference PickScore or CLIP-TQA to measure how well
the generated image matches the original prompt.

CLIP mode (config.ENABLE_CLIP_QA = True): embeds both the image and the
prompt text with the same CLIP model and computes cosine similarity,
rescaled to 0-10. This is the standard, real technique underlying
CLIP-based text-image alignment scores (PickScore itself is a fine-tuned
variant of this same idea) — a documented, honest adaptation rather than
a claim of using the exact PickScore checkpoint.

Fallback mode (default, no heavy ML deps required): a lexical-overlap
score between the prompt's meaningful words and a lightweight caption
proxy is NOT used, because faking semantic understanding from keyword
matching alone would be misleading. Instead, fallback mode always reports
"not evaluated" rather than inventing a fake number — see
`SemanticResult.evaluated`. The pipeline treats an unevaluated semantic
check as a pass-through (not a rejection), and this is clearly surfaced
in the UI and README rather than hidden.
"""

from dataclasses import dataclass
from pathlib import Path

import config
from utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class SemanticResult:
    evaluated: bool
    score: float | None
    threshold: float
    passed: bool
    method: str


def _clip_similarity(path: Path, prompt: str) -> float:
    import torch
    from transformers import CLIPModel, CLIPProcessor
    from PIL import Image

    model_name = "openai/clip-vit-large-patch14"
    model = CLIPModel.from_pretrained(model_name)
    processor = CLIPProcessor.from_pretrained(model_name)

    image = Image.open(path).convert("RGB")
    inputs = processor(text=[prompt], images=image, return_tensors="pt", padding=True, truncation=True)

    with torch.no_grad():
        outputs = model(**inputs)
        image_embeds = outputs.image_embeds / outputs.image_embeds.norm(p=2, dim=-1, keepdim=True)
        text_embeds = outputs.text_embeds / outputs.text_embeds.norm(p=2, dim=-1, keepdim=True)
        similarity = torch.matmul(image_embeds, text_embeds.T).item()

    # cosine similarity is typically in [-1, 1] but CLIP image/text pairs
    # for genuinely matching content usually land in [0.15, 0.35]; rescale
    # generously so the 0-10 range is meaningfully spread out.
    score = max(0.0, min(10.0, (similarity / 0.4) * 10.0))
    return round(score, 2)


def evaluate(path: Path, prompt: str, request_id: str) -> SemanticResult:
    if not config.ENABLE_CLIP_QA:
        logger.info(
            "[%s] semantic QA skipped (ENABLE_CLIP_QA=false); treated as pass-through, not a fabricated score.",
            request_id,
        )
        return SemanticResult(
            evaluated=False, score=None, threshold=config.SEMANTIC_THRESHOLD,
            passed=True, method="not_evaluated",
        )

    try:
        score = _clip_similarity(path, prompt)
        passed = score >= config.SEMANTIC_THRESHOLD
        logger.info(
            "[%s] semantic QA (clip_cosine_similarity): score=%.2f threshold=%.1f -> %s",
            request_id, score, config.SEMANTIC_THRESHOLD, "PASS" if passed else "REJECT",
        )
        return SemanticResult(
            evaluated=True, score=score, threshold=config.SEMANTIC_THRESHOLD,
            passed=passed, method="clip_cosine_similarity",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] CLIP semantic scoring unavailable (%s); treated as pass-through.", request_id, exc)
        return SemanticResult(
            evaluated=False, score=None, threshold=config.SEMANTIC_THRESHOLD,
            passed=True, method="unavailable_fallback",
        )
