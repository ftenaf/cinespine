#!/bin/bash
# CineSpine Replit Deployment Startup Script

# 1. Handle Google Application Credentials dynamically for Replit Secrets
if [ -n "$GCP_CREDENTIALS_JSON" ]; then
    echo "Writing Google Application Credentials from environment secret..."
    echo "$GCP_CREDENTIALS_JSON" > gcp-credentials.json
    export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/gcp-credentials.json"
fi

# 2. Start the unified FastAPI application
# (This serves the API on /api and the compiled React frontend assets)
echo "Starting CineSpine unified backend..."
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
