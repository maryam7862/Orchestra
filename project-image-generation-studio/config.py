"""
config.py
=========
Single source of truth for every tunable value in the app.

Nothing outside this file should hard-code a timeout, a resolution,
a threshold, or a directory path. That is intentional (see Project 3
slide requirement: "do not scatter magic numbers").
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


def _resolve_writable_dir(relative_name: str) -> Path:
    """Use the project root when writable, otherwise fall back to /tmp.

    Vercel's filesystem is read-only outside /tmp, so directory creation must
    never crash during import.
    """
    candidates = [
        BASE_DIR / relative_name,
        Path("/tmp") / "project-image-generation-studio" / relative_name,
    ]

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue

    fallback = Path("/tmp") / "project-image-generation-studio" / relative_name
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def load_env_files(project_root: Path | None = None) -> None:
    """Load environment variables from the usual local files.

    .env.local is treated as the project-specific override file, while the
    process environment still wins if a variable is already set.
    """
    root = (project_root or BASE_DIR).resolve()

    # .env is the standard project file; .env.local is a common convenience
    # override used in this repo and should win when both are present.
    for env_file in (root / ".env", root / ".env.local"):
        if env_file.exists():
            load_dotenv(env_file, override=False)

    local_override = root / ".env.local"
    if local_override.exists():
        load_dotenv(local_override, override=True)


load_env_files()

# ---------------------------------------------------------------------------
# Hugging Face
# ---------------------------------------------------------------------------
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()

# The current working free-tier route in practice is FLUX.1-schnell.
# Keep FLUX.1-dev as a fallback only when the active provider route is not
# available, but do not default to it because it has been hitting payment/
# credit exhaustion on some accounts.
# Check: https://huggingface.co/docs/inference-providers
HF_MODEL = os.environ.get("HF_MODEL", "black-forest-labs/FLUX.1-schnell").strip()

HF_MODEL_FALLBACKS = (
    "black-forest-labs/FLUX.1-schnell",
    "black-forest-labs/FLUX.1-dev",
)

# Optional: pin a specific inference provider (e.g. "fal-ai", "replicate",
# "hf-inference"). Leave blank to let huggingface_hub choose automatically.
# NOTE: do not pass provider as a text_to_image() keyword argument; in the
# current SDK, provider belongs on InferenceClient(..., provider=...) not on the
# generation method itself.
HF_PROVIDER = os.environ.get("HF_PROVIDER", "").strip() or None

# ---------------------------------------------------------------------------
# Network / timeouts (Project 3 slides 8-10)
# ---------------------------------------------------------------------------
# 3.05s = just over a multiple of the common 3s TCP retransmission window,
# giving one retransmit a chance to land before we give up on the connect
# phase. This is the well-known "requests" library convention.
CONNECTION_TIMEOUT = 3.05

# Image generation can involve queueing on a shared/free GPU pool, so the
# read timeout is generous.
READ_TIMEOUT = 60

REQUEST_TIMEOUT = (CONNECTION_TIMEOUT, READ_TIMEOUT)

# ---------------------------------------------------------------------------
# Retry strategy (slide 11)
# ---------------------------------------------------------------------------
MAX_RETRY_ATTEMPTS = 4
RETRY_BASE_DELAY = 0.75          # seconds, doubled each attempt
RETRY_MAX_DELAY = 20.0
RETRY_JITTER = 0.4               # +/- fraction of the computed delay
RETRYABLE_STATUS_CODES = {429, 503}

# ---------------------------------------------------------------------------
# Streaming / binary handling (slide 13)
# ---------------------------------------------------------------------------
STREAM_CHUNK_SIZE = 65536  # 64 KiB, per Project 3 spec

# ---------------------------------------------------------------------------
# Aspect ratio -> exact resolution mapping (slide 7)
# ---------------------------------------------------------------------------
ASPECT_RATIOS = {
    "16:9": {
        "width": 1344,
        "height": 768,
        "pixel_volume": 1344 * 768,
        "label": "Landscape",
        "use_case": "Web banners / presentations",
    },
    "1:1": {
        "width": 1024,
        "height": 1024,
        "pixel_volume": 1024 * 1024,
        "label": "Square",
        "use_case": "Avatars / product grids",
    },
    "9:16": {
        "width": 768,
        "height": 1344,
        "pixel_volume": 768 * 1344,
        "label": "Vertical",
        "use_case": "Mobile reels / wallpapers",
    },
}

# FLUX.1-schnell (and most current HF diffusion routes) accept arbitrary
# width/height as long as both are multiples of 8 and within a sane range.
# All three Project 3 targets above satisfy that, so no compatibility
# down-mapping is needed today. If you swap in a model that only accepts
# fixed buckets (e.g. some SDXL Turbo routes), set this to True so
# payload_builder.py snaps to the nearest supported bucket instead of
# sending the exact Project 3 numbers, and reports the discrepancy.
REQUIRE_DIMENSION_COMPATIBILITY_CHECK = False
MODEL_DIMENSION_MULTIPLE = 8

# ---------------------------------------------------------------------------
# Generation limits
# ---------------------------------------------------------------------------
MAX_IMAGES_PER_REQUEST = 4
MODEL_SUPPORTS_BATCH = False  # HF InferenceClient.text_to_image is single-image
MODEL_SUPPORTS_NEGATIVE_PROMPT = True  # FLUX.1-schnell accepts negative_prompt via provider

MAX_GENERATION_ATTEMPTS = 3  # regeneration loop (slide 42)

# ---------------------------------------------------------------------------
# Prompt limits
# ---------------------------------------------------------------------------
MAX_PROMPT_CHARS = 2000
MAX_NEGATIVE_PROMPT_CHARS = 1000

# ---------------------------------------------------------------------------
# QA thresholds (slide 16)
# ---------------------------------------------------------------------------
# The default heuristic aesthetic scorer is intentionally conservative and
# can rate simple but valid compositions (e.g. a single object on a clean
# background) too harshly. Keep the threshold low enough that real generated
# images pass until the opt-in CLIP QA mode is enabled for stricter scoring.
AESTHETIC_THRESHOLD = 1.5       # out of 10
SEMANTIC_THRESHOLD = 5.0        # out of 10 (cosine-similarity based, see semantic_qa.py)

# Set to True only once you've installed torch + transformers and are happy
# waiting for a one-time ~600MB CLIP download. False uses a fast, fully
# local, deterministic image-statistics heuristic instead (documented in
# services/aesthetic_qa.py). Either mode NEVER returns a random score.
ENABLE_CLIP_QA = os.environ.get("ENABLE_CLIP_QA", "false").strip().lower() == "true"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
GENERATED_ASSETS_DIR = _resolve_writable_dir("generated_assets")
EXPORTS_DIR = _resolve_writable_dir("exports")
LOGS_DIR = _resolve_writable_dir("logs")
HISTORY_FILE = GENERATED_ASSETS_DIR / "history.json"

# ---------------------------------------------------------------------------
# Style presets (slide 19 / conclusion)
# ---------------------------------------------------------------------------
STYLE_PRESETS = {
    "none": "",
    "cyberpunk": "cyberpunk aesthetic, neon lighting, futuristic city, high contrast, cinematic",
    "minimalism": "minimalist composition, clean lines, negative space, muted palette",
    "cinematic": "cinematic lighting, dramatic shadows, film grain, wide dynamic range",
    "photorealistic": "photorealistic, ultra-detailed, natural lighting, sharp focus, 8k",
    "fantasy": "epic fantasy art, painterly detail, dramatic atmosphere, intricate detail",
    "editorial": "editorial photography style, studio lighting, high fashion, clean background",
}

# These are applied by APPENDING to the prompt text (payload_builder.py) —
# never sent as a fake "style" API parameter, since the provider has no such
# parameter (slide 92 requirement).
