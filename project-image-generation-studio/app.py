"""
app.py
======
Multimodal Image Generation Studio — Flask entry point.

Routes:
  GET  /                        -> main UI
  POST /api/generate            -> run the full pipeline for a new image
  POST /api/regenerate          -> re-run generation with the same payload
  GET  /api/history             -> recent generation history
  GET  /api/assets/<filename>   -> serve a generated image
  GET  /api/download/<filename> -> force-download a generated image
  POST /api/export/<kind>       -> Unreal / Blender / Polycam export packages
  GET  /api/health              -> safe health check (never exposes secrets)
"""

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, render_template, abort

import config
from services import pipeline, history
from integrations import unreal, blender, polycam
from utils.file_utils import resolve_within
from utils.logging_utils import get_logger

logger = get_logger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1MB request body cap (JSON only)


def error_response(code: str, message: str, http_status: int = 400):
    return jsonify({"success": False, "error": {"code": code, "message": message}}), http_status


def events_to_dicts(events):
    return [{"stage": e.stage, "status": e.status, "detail": e.detail} for e in events]


@app.route("/")
def index():
    return render_template(
        "index.html",
        aspect_ratios=config.ASPECT_RATIOS,
        style_presets=list(config.STYLE_PRESETS.keys()),
        max_images=config.MAX_IMAGES_PER_REQUEST,
        max_prompt_chars=config.MAX_PROMPT_CHARS,
        max_negative_chars=config.MAX_NEGATIVE_PROMPT_CHARS,
    )


def _run_pipeline_from_request():
    data = request.get_json(silent=True) or {}
    result = pipeline.run_generation(
        raw_prompt=data.get("prompt", ""),
        raw_negative_prompt=data.get("negative_prompt"),
        aspect_ratio=data.get("aspect_ratio", "1:1"),
        num_images=data.get("num_images", 1),
        style_preset=data.get("style_preset", "none"),
    )

    if not result.success:
        return jsonify({
            "success": False,
            "request_id": result.request_id,
            "events": events_to_dicts(result.events),
            "payload": result.payload,
            "attempts_used": result.attempts_used,
            "error": {"code": result.error_code, "message": result.error_message},
        }), 200  # 200: this is a well-formed, handled failure, not a server crash

    return jsonify({
        "success": True,
        "request_id": result.request_id,
        "events": events_to_dicts(result.events),
        "payload": result.payload,
        "image_url": result.image_url,
        "filename": Path(result.image_path).name,
        "integrity": result.integrity_info,
        "qa": result.qa_info,
        "attempts_used": result.attempts_used,
    })


@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        return _run_pipeline_from_request()
    except Exception as exc:  # noqa: BLE001 - last-resort guard, never leak stack traces
        logger.exception("Unhandled error in /api/generate")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred. Check server logs.", 500)


@app.route("/api/regenerate", methods=["POST"])
def api_regenerate():
    # Regeneration reuses the same validated inputs the client already
    # has (it just calls /api/generate again with the same form state) —
    # the bounded regeneration loop within a single pipeline run already
    # covers rejection-triggered regeneration. This endpoint exists for
    # an explicit user-triggered "try again" from the UI.
    try:
        return _run_pipeline_from_request()
    except Exception:
        logger.exception("Unhandled error in /api/regenerate")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred. Check server logs.", 500)


@app.route("/api/history")
def api_history():
    limit = request.args.get("limit", default=50, type=int)
    return jsonify({"success": True, "history": history.get_history(limit)})


@app.route("/api/assets/<path:filename>")
def api_assets(filename):
    try:
        path = resolve_within(config.GENERATED_ASSETS_DIR, filename)
    except ValueError:
        abort(400)
    if not path.exists():
        abort(404)
    return send_from_directory(config.GENERATED_ASSETS_DIR, path.name)


@app.route("/api/download/<path:filename>")
def api_download(filename):
    try:
        path = resolve_within(config.GENERATED_ASSETS_DIR, filename)
    except ValueError:
        abort(400)
    if not path.exists():
        abort(404)
    return send_from_directory(config.GENERATED_ASSETS_DIR, path.name, as_attachment=True)


@app.route("/api/export/<kind>", methods=["POST"])
def api_export(kind):
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    metadata = data.get("metadata", {})

    if not filename:
        return error_response("MISSING_FILENAME", "filename is required.")

    try:
        image_path = resolve_within(config.GENERATED_ASSETS_DIR, filename)
    except ValueError:
        return error_response("INVALID_FILENAME", "Invalid filename.")

    if not image_path.exists():
        return error_response("NOT_FOUND", "Asset not found. Only verified, QA-accepted assets can be exported.", 404)

    exporters = {"unreal": unreal.export_for_unreal, "blender": blender.export_for_blender, "polycam": polycam.export_for_polycam}
    if kind not in exporters:
        return error_response("UNKNOWN_EXPORT_KIND", f"Unknown export target '{kind}'.")

    export_dir = exporters[kind](image_path, metadata, metadata.get("request_id", "export"))
    return jsonify({"success": True, "export_path": str(export_dir)})


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "service": "multimodal-image-generation-studio",
        "hf_token_configured": bool(config.HF_TOKEN),
        "model": config.HF_MODEL,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
