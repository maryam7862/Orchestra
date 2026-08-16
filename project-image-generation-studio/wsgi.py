"""
WSGI entry point for Vercel.

Vercel looks for a top-level 'app' variable to use as the WSGI application.
"""

import sys
import logging
from flask import Flask, jsonify

# Setup basic logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Create the Flask app instance at module level for Vercel to find
app = Flask(__name__)

# Try to import and use the actual app from app.py
try:
    logger.info("Attempting to import main app from app.py...")
    from app import app as actual_app
    # Replace our placeholder with the real one
    app = actual_app
    logger.info("✓ Successfully imported main app")
except Exception as e:
    logger.error(f"✗ Failed to import main app: {e}", exc_info=True)
    
    # Use minimal fallback app for debugging
    @app.route('/')
    def error_index():
        return jsonify({
            "error": "Failed to load application",
            "message": str(e),
            "type": type(e).__name__
        }), 500
    
    @app.route('/api/health')
    def health():
        return jsonify({"status": "error", "reason": str(e)}), 500

if __name__ == '__main__':
    app.run()

