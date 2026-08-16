"""
Multimodal Image Generation Studio
Flask application entry point.

Vercel entry point:
    app

Local development:
    python app.py
"""

from pathlib import Path

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    render_template,
    abort,
)


# ============================================================
# FLASK APPLICATION
# ============================================================
# IMPORTANT:
# Keep this as a simple top-level Flask instance.
# Vercel detects this variable as the WSGI application.

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

# Ensure required directories exist (important for Vercel's ephemeral filesystem)
def _ensure_writeable_dir(relative_name: str) -> Path:
    """Create a writable directory, falling back to /tmp when the app root is read-only."""
    candidates = [
        Path(relative_name),
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


for directory in ["logs", "generated_assets"]:
    _ensure_writeable_dir(directory)


# ============================================================
# HELPERS
# ============================================================

def get_logger():
    """Load project logger with a safe fallback."""
    try:
        from utils.logging_utils import get_logger as project_logger
        return project_logger()
    except Exception:
        import logging
        return logging.getLogger("image-generation-studio")


def get_config():
    """Load project configuration."""
    import config
    return config


def error_response(code, message, http_status=400):
    """Return a standard JSON error response."""
    return (
        jsonify(
            {
                "success": False,
                "error": {
                    "code": code,
                    "message": message,
                },
            }
        ),
        http_status,
    )


def events_to_dicts(events):
    """Convert pipeline events into JSON-safe dictionaries."""
    if not events:
        return []

    return [
        {
            "stage": getattr(event, "stage", ""),
            "status": getattr(event, "status", ""),
            "detail": getattr(event, "detail", ""),
        }
        for event in events
    ]


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health")
def health_check():
    """Simple health check endpoint."""
    import os
    return jsonify({
        "status": "ok",
        "hf_token": bool(os.environ.get("HF_TOKEN")),
        "hf_model": os.environ.get("HF_MODEL", "NOT SET")
    })


# ============================================================
# MAIN PAGE
# ============================================================

@app.route("/")
def index():
    """Render the main application."""
    try:
        config = get_config()

        return render_template(
            "index.html",
            aspect_ratios=getattr(
                config,
                "ASPECT_RATIOS",
                ["1:1"],
            ),
            style_presets=list(
                getattr(
                    config,
                    "STYLE_PRESETS",
                    {"none": {}},
                ).keys()
            ),
            max_images=getattr(
                config,
                "MAX_IMAGES_PER_REQUEST",
                1,
            ),
            max_prompt_chars=getattr(
                config,
                "MAX_PROMPT_CHARS",
                2000,
            ),
            max_negative_chars=getattr(
                config,
                "MAX_NEGATIVE_PROMPT_CHARS",
                1000,
            ),
        )

    except Exception:
        logger = get_logger()
        logger.exception("Failed to load main page")

        return error_response(
            "APP_STARTUP_ERROR",
            "The application could not load its configuration.",
            500,
        )


# ============================================================
# IMAGE GENERATION
# ============================================================

def _run_pipeline_from_request():
    """Run the image-generation pipeline."""

    data = request.get_json(silent=True) or {}

    # Import only when this endpoint is requested.
    from services import pipeline

    result = pipeline.run_generation(
        raw_prompt=data.get("prompt", ""),
        raw_negative_prompt=data.get("negative_prompt"),
        aspect_ratio=data.get("aspect_ratio", "1:1"),
        num_images=data.get("num_images", 1),
        style_preset=data.get("style_preset", "none"),
    )

    if not result.success:
        return (
            jsonify(
                {
                    "success": False,
                    "request_id": result.request_id,
                    "events": events_to_dicts(result.events),
                    "payload": result.payload,
                    "attempts_used": result.attempts_used,
                    "error": {
                        "code": result.error_code,
                        "message": result.error_message,
                    },
                }
            ),
            200,
        )

    filename = None

    if getattr(result, "image_path", None):
        filename = Path(result.image_path).name

    return jsonify(
        {
            "success": True,
            "request_id": result.request_id,
            "events": events_to_dicts(result.events),
            "payload": result.payload,
            "image_url": result.image_url,
            "filename": filename,
            "integrity": result.integrity_info,
            "qa": result.qa_info,
            "attempts_used": result.attempts_used,
        }
    )


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate a new image."""
    logger = get_logger()

    try:
        return _run_pipeline_from_request()

    except Exception:
        logger.exception("Unhandled error in /api/generate")

        return error_response(
            "INTERNAL_ERROR",
            "Image generation failed. Check server logs.",
            500,
        )


@app.route("/api/regenerate", methods=["POST"])
def api_regenerate():
    """Regenerate an image."""
    logger = get_logger()

    try:
        return _run_pipeline_from_request()

    except Exception:
        logger.exception("Unhandled error in /api/regenerate")

        return error_response(
            "INTERNAL_ERROR",
            "Image regeneration failed. Check server logs.",
            500,
        )


# ============================================================
# HISTORY
# ============================================================

@app.route("/api/history")
def api_history():
    """Return recent generation history."""
    try:
        from services import history

        limit = request.args.get(
            "limit",
            default=50,
            type=int,
        )

        limit = max(1, min(limit, 100))

        return jsonify(
            {
                "success": True,
                "history": history.get_history(limit),
            }
        )

    except Exception:
        logger = get_logger()
        logger.exception("Failed to load history")

        return error_response(
            "HISTORY_ERROR",
            "Could not load generation history.",
            500,
        )


# ============================================================
# ASSETS
# ============================================================

def _resolve_asset(filename):
    """Safely resolve a generated asset path."""
    config = get_config()

    from utils.file_utils import resolve_within

    return resolve_within(
        config.GENERATED_ASSETS_DIR,
        filename,
    )


@app.route("/api/assets/<path:filename>")
def api_assets(filename):
    """Serve a generated image."""
    try:
        path = _resolve_asset(filename)

    except ValueError:
        abort(400)

    except Exception:
        logger = get_logger()
        logger.exception("Could not resolve asset")
        abort(500)

    if not path.exists() or not path.is_file():
        abort(404)

    config = get_config()

    return send_from_directory(
        config.GENERATED_ASSETS_DIR,
        path.name,
    )


@app.route("/api/download/<path:filename>")
def api_download(filename):
    """Download a generated image."""
    try:
        path = _resolve_asset(filename)

    except ValueError:
        abort(400)

    except Exception:
        logger = get_logger()
        logger.exception("Could not resolve download")
        abort(500)

    if not path.exists() or not path.is_file():
        abort(404)

    config = get_config()

    return send_from_directory(
        config.GENERATED_ASSETS_DIR,
        path.name,
        as_attachment=True,
    )


# ============================================================
# EXPORTS
# ============================================================

@app.route("/api/export/<kind>", methods=["POST"])
def api_export(kind):
    """Export generated assets."""

    try:
        data = request.get_json(silent=True) or {}

        filename = data.get("filename")
        metadata = data.get("metadata", {})

        if not filename:
            return error_response(
                "MISSING_FILENAME",
                "filename is required.",
            )

        try:
            image_path = _resolve_asset(filename)

        except ValueError:
            return error_response(
                "INVALID_FILENAME",
                "Invalid filename.",
            )

        if not image_path.exists() or not image_path.is_file():
            return error_response(
                "NOT_FOUND",
                "Asset not found.",
                404,
            )

        if kind == "unreal":
            from integrations import unreal
            exporter = unreal.export_for_unreal

        elif kind == "blender":
            from integrations import blender
            exporter = blender.export_for_blender

        elif kind == "polycam":
            from integrations import polycam
            exporter = polycam.export_for_polycam

        else:
            return error_response(
                "UNKNOWN_EXPORT_KIND",
                f"Unknown export target '{kind}'.",
            )

        request_id = metadata.get(
            "request_id",
            "export",
        )

        export_dir = exporter(
            image_path,
            metadata,
            request_id,
        )

        return jsonify(
            {
                "success": True,
                "export_path": str(export_dir),
            }
        )

    except Exception:
        logger = get_logger()
        logger.exception("Export failed")

        return error_response(
            "EXPORT_ERROR",
            "The export operation failed.",
            500,
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health")
def api_health():
    """Safe health-check endpoint."""

    try:
        config = get_config()

        return jsonify(
            {
                "status": "ok",
                "service": "multimodal-image-generation-studio",
                "hf_token_configured": bool(
                    getattr(config, "HF_TOKEN", None)
                ),
                "model": getattr(
                    config,
                    "HF_MODEL",
                    None,
                ),
            }
        )

    except Exception:
        logger = get_logger()
        logger.exception("Health check failed")

        return jsonify(
            {
                "status": "error",
                "service": "multimodal-image-generation-studio",
                "hf_token_configured": False,
                "model": None,
            }
        ), 500


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================
# Vercel imports the top-level "app" variable above.
# This block only runs when you execute:
#
#     python app.py
#

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
    )




