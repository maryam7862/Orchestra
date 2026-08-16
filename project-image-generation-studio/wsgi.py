"""
WSGI entry point for Vercel.

Vercel looks for a top-level 'app' variable to use as the WSGI application.
"""

from flask import Flask, jsonify

# Create the Flask app instance at module level for Vercel to find
app = Flask(__name__)

# Try to import and use the actual app from app.py
try:
    from app import app as actual_app
    # Replace our placeholder with the real one
    app = actual_app
except Exception as e:
    import logging
    logging.error(f"Failed to import main app: {e}")
    
    # Use minimal fallback app for debugging
    @app.route('/')
    def error():
        return jsonify({
            "error": "Failed to load application",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    app.run()

