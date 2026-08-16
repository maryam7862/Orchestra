"""
WSGI entry point for Vercel.

This file exists to ensure the Flask app can be imported without
dependency errors. Vercel will use this to find the 'app' instance.
"""

try:
    from app import app
except ImportError as e:
    import logging
    logging.error(f"Failed to import Flask app: {e}")
    
    # Fallback: create a minimal app for debugging
    from flask import Flask, jsonify
    
    app = Flask(__name__)
    
    @app.route('/')
    def error():
        return jsonify({
            "error": "Flask app failed to import",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    app.run()
