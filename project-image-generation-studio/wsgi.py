"""
WSGI entry point for Vercel.

This module ensures Flask app initialization with detailed error reporting.
"""

import sys
import os
from pathlib import Path

# Ensure required directories exist before importing anything
for directory in ["logs", "generated_assets", "templates", "static"]:
    Path(directory).mkdir(parents=True, exist_ok=True)

import logging
import traceback
from flask import Flask, jsonify

# Setup basic logging to stdout for Vercel logs
logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create the Flask app instance at module level for Vercel to find
app = Flask(__name__, template_folder='templates', static_folder='static')

# Global error storage for debugging
_init_error = None

logger.info("=" * 60)
logger.info("WSGI STARTUP: Starting to import main app...")
logger.info("=" * 60)

try:
    logger.info("Python version: %s", sys.version)
    logger.info("Current directory: %s", os.getcwd())
    logger.info("HF_TOKEN present: %s", bool(os.environ.get("HF_TOKEN")))
    logger.info("HF_MODEL: %s", os.environ.get("HF_MODEL", "NOT SET"))
    
    logger.info("Checking required files...")
    for required_file in ["templates/index.html", "static/css/style.css", "static/js/app.js"]:
        exists = Path(required_file).exists()
        logger.info(f"  {required_file}: {'✓' if exists else '✗'}")
    
    logger.info("Attempting to import config...")
    import config
    logger.info("✓ Config imported successfully")
    logger.info("HF_TOKEN from config: %s", bool(config.HF_TOKEN))
    
    logger.info("Attempting to import app from app.py...")
    from app import app as actual_app
    app = actual_app
    logger.info("✓ Successfully imported main app from app.py")
    
except Exception as e:
    _init_error = e
    error_msg = traceback.format_exc()
    logger.error("✗ FAILED TO IMPORT APP")
    logger.error(error_msg)
    
    # Minimal fallback app
    @app.route('/')
    def error_index():
        return jsonify({
            "error": "Application failed to initialize",
            "error_type": type(_init_error).__name__,
            "error_message": str(_init_error),
            "traceback": error_msg.split('\n'),
            "cwd": os.getcwd(),
            "env_vars": {
                "HF_TOKEN": bool(os.environ.get("HF_TOKEN")),
                "HF_MODEL": os.environ.get("HF_MODEL", "NOT SET")
            }
        }), 500
    
    @app.route('/api/health')
    def health():
        return jsonify({
            "status": "error",
            "error": str(_init_error)
        }), 500

logger.info("=" * 60)
logger.info("WSGI STARTUP: Complete")
logger.info("=" * 60)

if __name__ == '__main__':
    app.run(debug=True)




