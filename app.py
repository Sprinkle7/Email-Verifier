"""
Flask API for email verification
Deployable on Render.com
"""

from flask import Flask, request, jsonify
from email_verifier import verify_email
import logging
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint for Render.com"""
    return jsonify({'status': 'ok', 'service': 'email_verifier'})


@app.route('/verify', methods=['POST'])
def verify():
    """
    Verify email address endpoint.
    Accepts JSON: {"email": "test@example.com"}
    Returns verification results.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        email = data.get('email')
        
        if not email:
            return jsonify({'error': 'Email field is required'}), 400
        
        if not isinstance(email, str):
            return jsonify({'error': 'Email must be a string'}), 400
        
        # Verify email
        logger.info(f"Verifying email: {email}")
        result = verify_email(email)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error verifying email: {str(e)}")
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


if __name__ == '__main__':
    # For local development
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
