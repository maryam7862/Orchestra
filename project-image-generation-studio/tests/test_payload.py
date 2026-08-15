import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from services import payload_builder
import config


def test_build_payload_16_9_maps_exact_resolution():
    p = payload_builder.build_payload("req-1", "a cat", None, "16:9", 1)
    assert p.width == 1344
    assert p.height == 768
    assert p.pixel_volume == 1344 * 768


def test_build_payload_1_1():
    p = payload_builder.build_payload("req-2", "a cat", None, "1:1", 1)
    assert (p.width, p.height) == (1024, 1024)


def test_build_payload_9_16():
    p = payload_builder.build_payload("req-3", "a cat", None, "9:16", 1)
    assert (p.width, p.height) == (768, 1344)


def test_empty_prompt_rejected():
    with pytest.raises(payload_builder.PayloadValidationError):
        payload_builder.build_payload("req-4", "   ", None, "1:1", 1)


def test_prompt_too_long_rejected():
    long_prompt = "a" * (config.MAX_PROMPT_CHARS + 1)
    with pytest.raises(payload_builder.PayloadValidationError):
        payload_builder.build_payload("req-5", long_prompt, None, "1:1", 1)


def test_invalid_aspect_ratio_rejected():
    with pytest.raises(payload_builder.PayloadValidationError):
        payload_builder.build_payload("req-6", "a cat", None, "4:3", 1)


def test_num_images_out_of_range_rejected():
    with pytest.raises(payload_builder.PayloadValidationError):
        payload_builder.build_payload("req-7", "a cat", None, "1:1", config.MAX_IMAGES_PER_REQUEST + 1)


def test_negative_prompt_included_when_supported():
    p = payload_builder.build_payload("req-8", "a cat", "blurry", "1:1", 1)
    if config.MODEL_SUPPORTS_NEGATIVE_PROMPT:
        assert p.negative_prompt == "blurry"
    else:
        assert p.negative_prompt is None


def test_style_preset_appends_to_prompt():
    p = payload_builder.build_payload("req-9", "a city", None, "1:1", 1, style_preset="cyberpunk")
    assert "cyberpunk" in p.prompt.lower()
