"""
services/payload_builder.py
============================
STAGE 1 of the six-stage blueprint: Prompt / Payload Formulation.

Responsible for:
  1. receiving prompt + negative prompt
  2. validating both
  3. validating aspect ratio
  4. mapping aspect ratio -> exact Project 3 resolution
  5. validating generation count
  6. applying style presets (by text augmentation, not fake API params)
  7. building a provider-agnostic, serializable payload
  8. never leaking secrets into the payload
"""

from dataclasses import dataclass, asdict
from typing import Optional

import config


class PayloadValidationError(ValueError):
    """Raised when user input fails validation. Never retried."""


@dataclass
class GenerationPayload:
    request_id: str
    prompt: str
    negative_prompt: Optional[str]
    negative_prompt_supported: bool
    aspect_ratio: str
    width: int
    height: int
    pixel_volume: int
    num_images: int
    style_preset: str
    model: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_safe_dict(self) -> dict:
        """Version of the payload that is safe to show in the UI's
        Payload Inspector — identical to to_dict() today because this
        payload never contains secrets, but kept separate so future
        fields can't leak by accident."""
        return self.to_dict()


def _validate_prompt(prompt: str) -> str:
    if prompt is None:
        raise PayloadValidationError("Prompt is required.")
    prompt = prompt.strip()
    if not prompt:
        raise PayloadValidationError("Prompt cannot be empty.")
    if len(prompt) > config.MAX_PROMPT_CHARS:
        raise PayloadValidationError(
            f"Prompt exceeds {config.MAX_PROMPT_CHARS} character limit."
        )
    return prompt


def _validate_negative_prompt(negative_prompt: Optional[str]) -> Optional[str]:
    if not negative_prompt:
        return None
    negative_prompt = negative_prompt.strip()
    if not negative_prompt:
        return None
    if len(negative_prompt) > config.MAX_NEGATIVE_PROMPT_CHARS:
        raise PayloadValidationError(
            f"Negative prompt exceeds {config.MAX_NEGATIVE_PROMPT_CHARS} character limit."
        )
    return negative_prompt


def _validate_aspect_ratio(aspect_ratio: str) -> dict:
    if aspect_ratio not in config.ASPECT_RATIOS:
        valid = ", ".join(config.ASPECT_RATIOS.keys())
        raise PayloadValidationError(
            f"Unsupported aspect ratio '{aspect_ratio}'. Valid options: {valid}."
        )
    return config.ASPECT_RATIOS[aspect_ratio]


def _validate_num_images(num_images: int) -> int:
    try:
        num_images = int(num_images)
    except (TypeError, ValueError):
        raise PayloadValidationError("Number of images must be an integer.")
    if num_images < 1 or num_images > config.MAX_IMAGES_PER_REQUEST:
        raise PayloadValidationError(
            f"Number of images must be between 1 and {config.MAX_IMAGES_PER_REQUEST}."
        )
    return num_images


def _validate_dimensions(width: int, height: int) -> None:
    """
    Guards against the 'exact API handshake failure' the slides warn about:
    never send arbitrary dimensions. Both must be multiples of the model's
    required step size (8 for FLUX.1-schnell and most current diffusion
    routes on Hugging Face).
    """
    if width % config.MODEL_DIMENSION_MULTIPLE or height % config.MODEL_DIMENSION_MULTIPLE:
        raise PayloadValidationError(
            "Internal resolution mapping is invalid for the current model "
            "(dimensions must be multiples of "
            f"{config.MODEL_DIMENSION_MULTIPLE})."
        )


def apply_style_preset(prompt: str, style_preset: str) -> str:
    style_preset = (style_preset or "none").lower()
    suffix = config.STYLE_PRESETS.get(style_preset, "")
    if style_preset not in config.STYLE_PRESETS:
        # Unknown preset name -> treat as "custom style", already embedded
        # in the prompt text by the caller, so nothing to append here.
        return prompt
    if not suffix:
        return prompt
    return f"{prompt}, {suffix}"


def build_payload(
    request_id: str,
    raw_prompt: str,
    raw_negative_prompt: Optional[str],
    aspect_ratio: str,
    num_images: int,
    style_preset: str = "none",
) -> GenerationPayload:
    prompt = _validate_prompt(raw_prompt)
    negative_prompt = _validate_negative_prompt(raw_negative_prompt)
    ratio_info = _validate_aspect_ratio(aspect_ratio)
    num_images = _validate_num_images(num_images)

    width, height = ratio_info["width"], ratio_info["height"]
    _validate_dimensions(width, height)

    prompt = apply_style_preset(prompt, style_preset)

    negative_prompt_supported = config.MODEL_SUPPORTS_NEGATIVE_PROMPT
    effective_negative_prompt = negative_prompt if negative_prompt_supported else None

    return GenerationPayload(
        request_id=request_id,
        prompt=prompt,
        negative_prompt=effective_negative_prompt,
        negative_prompt_supported=negative_prompt_supported,
        aspect_ratio=aspect_ratio,
        width=width,
        height=height,
        pixel_volume=ratio_info["pixel_volume"],
        num_images=num_images,
        style_preset=style_preset,
        model=config.HF_MODEL,
    )
