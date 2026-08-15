```python
"""
app.py
======
Multimodal Image Generation Studio — Flask entry point.

Vercel-compatible Flask application.

Routes:
  GET  /                        -> main UI
  POST /api/generate            -> run the image generation pipeline
  POST /api/regenerate          -> regenerate an image
  GET  /api/history             -> recent generation history
  GET  /api/assets/<filename>   -> serve a generated image
  GET  /api/download/<filename> -> download a generated image
  POST /api/export/<kind>       -> Unreal / Blender / Polycam export
  GET  /api/health              -> health check
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

# ---------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)

# Keep JSON requests reasonably small.
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024


# ---------------------------------------------------------------------
# Safe helpers
# ---------------------------------------------------------------------

def error_response(
    code: str,
    message: str,
    http_status: int = 400,
):
    """Return a consistent JSON error response."""
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


def get_config():
    """
    Import config only when needed.

    Lazy importing helps prevent the entire Flask application from
    failing during serverless startup if a project-specific dependency
    or configuration has an issue.
    """
    import config

    return config


def get_logger():
    """Load the project logger safely."""
    try:
        from utils.logging_utils import get_logger as project_logger

        return project_logger()
    except Exception:
        import logging

        return logging.getLogger("image-generation-studio")


def events_to_dicts(events):
    """Convert pipeline event objects into JSON-compatible dictionaries."""
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


# ---------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------

@app.route("/")
def index():
    """Render the main application interface."""
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
        logger.exception("Failed to load the main page")

        return error_response(
            "APP_STARTUP_ERROR",
            "The application could not load its configuration.",
            500,
        )


# ---------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------

def _run_pipeline_from_request():
    """Read the request and run the image generation pipeline."""

    data = request.get_json(silent=True) or {}

    # Import only when the endpoint is actually called.
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

    return jsonify(
        {
            "success": True,
            "request_id": result.request_id,
            "events": events_to_dicts(result.events),
            "payload": result.payload,
            "image_url": result.image_url,
            "filename": (
                Path(result.image_path).name
                if result.image_path
                else None
            ),
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
            "Image generation failed. Check the server logs.",
            500,
        )


@app.route("/api/regenerate", methods=["POST"])
def api_regenerate():
    """Regenerate an image using the same request structure."""
    logger = get_logger()

    try:
        return _run_pipeline_from_request()

    except Exception:
        logger.exception("Unhandled error in /api/regenerate")

        return error_response(
            "INTERNAL_ERROR",
            "Image regeneration failed. Check the server logs.",
            500,
        )


# ---------------------------------------------------------------------
# History
# ---------------------------------------------------------------------

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

        # Keep the value bounded.
        limit = max(1, min(limit, 100))

        return jsonify(
            {
                "success": True,
                "history": history.get_history(limit),
            }
        )

    except Exception:
        logger = get_logger()
        logger.exception("Failed to load generation history")

        return error_response(
            "HISTORY_ERROR",
            "Could not load generation history.",
            500,
        )


# ---------------------------------------------------------------------
# Generated assets
# ---------------------------------------------------------------------

def _get_asset_path(filename):
    """Resolve a generated asset safely."""
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
        path = _get_asset_path(filename)

    except ValueError:
        abort(400)

    except Exception:
        logger = get_logger()
        logger.exception("Could not resolve generated asset")
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
    """Force-download a generated image."""
    try:
        path = _get_asset_path(filename)

    except ValueError:
        abort(400)

    except Exception:
        logger = get_logger()
        logger.exception("Could not resolve download asset")
        abort(500)

    if not path.exists() or not path.is_file():
        abort(404)

    config = get_config()

    return send_from_directory(
        config.GENERATED_ASSETS_DIR,
        path.name,
        as_attachment=True,
    )


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------

@app.route("/api/export/<kind>", methods=["POST"])
def api_export(kind):
    """Export a verified generated image."""
    try:
        config = get_config()

        data = request.get_json(silent=True) or {}

        filename = data.get("filename")
        metadata = data.get("metadata", {})

        if not filename:
            return error_response(
                "MISSING_FILENAME",
                "filename is required.",
            )

        try:
            image_path = _get_asset_path(filename)

        except ValueError:
            return error_response(
                "INVALID_FILENAME",
                "Invalid filename.",
            )

        if not image_path.exists() or not image_path.is_file():
            return error_response(
                "NOT_FOUND",
                "Asset not found. Only verified, QA-accepted assets can be exported.",
                404,
            )

        # Import exporters only when required.
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


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------

@app.route("/api/health")
def api_health():
    """
    Safe health check.

    Does not expose the actual Hugging Face token.
    """
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

    except Exception as exc:
        logger = get_logger()
        logger.exception("Health check configuration error")

        return jsonify(
            {
                "status": "degraded",
                "service": "multimodal-image-generation-studio",
                "hf_token_configured": False,
                "error": str(exc),
            }
        ), 500


# ---------------------------------------------------------------------
# Vercel / local execution
# ---------------------------------------------------------------------

# Vercel imports the variable named "app" above.
#
# This block is ONLY executed when running the file directly:
#
#     python app.py
#
# It will NOT execute when Vercel imports the Flask application.

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False,
    )
```

