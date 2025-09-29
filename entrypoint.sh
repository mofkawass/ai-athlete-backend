#!/usr/bin/env bash
set -e
if [ -n "$GCP_SERVICE_ACCOUNT_JSON_BASE64" ]; then
  echo "$GCP_SERVICE_ACCOUNT_JSON_BASE64" | base64 -d > /app/gcp.json
fi
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
