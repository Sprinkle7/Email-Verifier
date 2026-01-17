#!/bin/bash
# Startup script for AWS EC2 deployment

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Get port from environment or default to 5000
PORT=${PORT:-5000}

# Start gunicorn
gunicorn app:app \
    --bind 0.0.0.0:$PORT \
    --workers 4 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
