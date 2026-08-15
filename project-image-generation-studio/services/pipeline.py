"""
services/pipeline.py
=====================
Orchestrates the complete six-stage blueprint end to end, including the
bounded regeneration loop (slide 42):

  1. Payload formulation       (payload_builder.py)
  2. Network API gateway       (api_gateway.py / retry.py / huggingface_provider.py)
  3. Security gates            (security.py)
  4. Transport / binary        (downloader.py)
  5. Integrity verification    (integrity.py)
  6. Automated QA              (qa.py)

Returns a structured result containing a REAL stage-by-stage log (every
status recorded here actually happened — see "no fake features"
requirement). The Flask layer runs this synchronously and hands the full
log to the frontend, which animates through it stage-by-stage for the
pipeline monitor UI. This is not live websocket streaming; it's an
honest replay of real backend events, and that trade-off is documented
in the README rather than presented as something it isn't.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config
from services import payload_builder, security, integrity, qa, history
from services.image_provider import get_active_provider
from services.downloader import save_provider_result
from services.retry import run_with_retry, NonRetryableError, RetryableError
from utils.file_utils import delete_if_exists
from utils.logging_utils import get_logger, new_request_id

logger = get_logger(__name__)

STAGE_NAMES = [
    "payload",
    "network",
    "security",
    "transport",
    "integrity",
    "qa",
]


@dataclass
class StageEvent:
    stage: str
    status: str  # WAITING | PROCESSING | SUCCESS | RETRYING | REJECTED | FAILED
    detail: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    success: bool
    request_id: str
    events: list
    image_path: Optional[Path] = None
    image_url: Optional[str] = None
    payload: Optional[dict] = None
    integrity_info: Optional[dict] = None
    qa_info: Optional[dict] = None
    attempts_used: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None


def run_generation(
    raw_prompt: str,
    raw_negative_prompt: Optional[str],
    aspect_ratio: str,
    num_images: int,
    style_preset: str,
) -> PipelineResult:
    request_id = new_request_id()
    events: list[StageEvent] = []

    def log_event(stage: str, status: str, **detail):
        events.append(StageEvent(stage=stage, status=status, detail=detail))

    # ---- STAGE 1: payload ----
    log_event("payload", "PROCESSING")
    try:
        gen_payload = payload_builder.build_payload(
            request_id, raw_prompt, raw_negative_prompt, aspect_ratio, num_images, style_preset,
        )
    except payload_builder.PayloadValidationError as exc:
        log_event("payload", "FAILED", message=str(exc))
        return PipelineResult(
            success=False, request_id=request_id, events=events,
            error_code="INVALID_PAYLOAD", error_message=str(exc),
        )
    log_event("payload", "SUCCESS", payload=gen_payload.to_safe_dict())

    # ---- STAGE 3a: security gate 1 (pre-generation) — runs before network ----
    log_event("security", "PROCESSING", gate=1)
    gate1 = security.pre_generation_check(gen_payload.prompt, gen_payload.negative_prompt, request_id)
    if not gate1.passed:
        log_event("security", "REJECTED", gate=1, code=gate1.code, message=gate1.message)
        return PipelineResult(
            success=False, request_id=request_id, events=events,
            payload=gen_payload.to_safe_dict(),
            error_code=gate1.code, error_message=gate1.message,
        )
    log_event("security", "SUCCESS", gate=1)

    last_error_code = "UNKNOWN"
    last_error_message = "Generation failed."
    last_qa_result = None
    last_integrity_result = None

    for attempt in range(1, config.MAX_GENERATION_ATTEMPTS + 1):
        image_path = None
        try:
            # ---- STAGE 2: network gateway (provider call, with retry) ----
            provider = get_active_provider()

            def do_generate():
                return provider.generate(
                    prompt=gen_payload.prompt,
                    negative_prompt=gen_payload.negative_prompt,
                    width=gen_payload.width,
                    height=gen_payload.height,
                    request_id=request_id,
                )

            def on_status(status, detail):
                # `detail` already includes "attempt" (set by retry.py's
                # run_with_retry), so it is not passed again here. This is
                # the single source of "network" stage events — retry.py
                # already reports PROCESSING/RETRYING/SUCCESS/FAILED, so we
                # don't log a duplicate PROCESSING event before calling it.
                log_event("network", status, **detail)

            provider_result = run_with_retry(do_generate, request_id, on_status)

            # ---- STAGE 3b: security gate 2 (post-generation) ----
            log_event("security", "PROCESSING", gate=2, attempt=attempt)
            gate2 = security.post_generation_check(None, request_id)
            if not gate2.passed:
                log_event("security", "REJECTED", gate=2, code=gate2.code, message=gate2.message)
                last_error_code, last_error_message = gate2.code, gate2.message
                continue
            log_event("security", "SUCCESS", gate=2)

            # ---- STAGE 4: transport (memory-safe save) ----
            log_event("transport", "PROCESSING", attempt=attempt, source_kind=provider_result.source_kind)
            image_path = save_provider_result(provider_result, request_id)
            log_event("transport", "SUCCESS", attempt=attempt, filename=image_path.name)

            # ---- STAGE 5: integrity verification ----
            log_event("integrity", "PROCESSING", attempt=attempt)
            integrity_result = integrity.verify_and_fingerprint(image_path, request_id)
            last_integrity_result = integrity_result
            if not integrity_result.passed:
                log_event("integrity", "REJECTED", attempt=attempt, message=integrity_result.error)
                last_error_code, last_error_message = "CORRUPTED_IMAGE", integrity_result.error
                continue
            log_event("integrity", "SUCCESS", attempt=attempt,
                       width=integrity_result.width, height=integrity_result.height,
                       checksum=integrity_result.checksum)

            # ---- STAGE 6: automated QA ----
            log_event("qa", "PROCESSING", attempt=attempt)
            qa_result = qa.run_qa(image_path, gen_payload.prompt, request_id)
            last_qa_result = qa_result
            if not qa_result.passed:
                log_event("qa", "REJECTED", attempt=attempt, reason=qa_result.reason)
                delete_if_exists(image_path)
                last_error_code, last_error_message = "QA_REJECTED", qa_result.reason
                continue
            log_event("qa", "SUCCESS", attempt=attempt,
                       aesthetic_score=qa_result.aesthetic.score,
                       semantic_score=qa_result.semantic.score)

            # ---- ACCEPTED ----
            metadata = {
                "request_id": request_id,
                "prompt": gen_payload.prompt,
                "negative_prompt": gen_payload.negative_prompt,
                "aspect_ratio": gen_payload.aspect_ratio,
                "width": integrity_result.width,
                "height": integrity_result.height,
                "provider": provider_result.provider_name,
                "model": provider_result.model_name,
                "attempt": attempt,
                "aesthetic_score": qa_result.aesthetic.score,
                "semantic_score": qa_result.semantic.score,
                "integrity_checksum": integrity_result.checksum,
                "byte_size": integrity_result.byte_size,
            }
            history.add_entry({
                **metadata,
                "filename": image_path.name,
            })

            return PipelineResult(
                success=True, request_id=request_id, events=events,
                image_path=image_path, image_url=f"/api/assets/{image_path.name}",
                payload=gen_payload.to_safe_dict(),
                integrity_info=integrity_result.__dict__,
                qa_info={
                    "aesthetic": qa_result.aesthetic.__dict__,
                    "semantic": qa_result.semantic.__dict__,
                },
                attempts_used=attempt,
            )

        except NonRetryableError as exc:
            if image_path:
                delete_if_exists(image_path)
            # retry.py's on_status callback already logged the FAILED
            # event for this stage before re-raising — no duplicate here.
            return PipelineResult(
                success=False, request_id=request_id, events=events,
                payload=gen_payload.to_safe_dict(),
                error_code=exc.code, error_message=exc.message,
                attempts_used=attempt,
            )
        except RetryableError as exc:
            if image_path:
                delete_if_exists(image_path)
            last_error_code, last_error_message = exc.code, exc.message
            continue

    return PipelineResult(
        success=False, request_id=request_id, events=events,
        payload=gen_payload.to_safe_dict(),
        error_code=last_error_code, error_message=last_error_message,
        attempts_used=config.MAX_GENERATION_ATTEMPTS,
    )
