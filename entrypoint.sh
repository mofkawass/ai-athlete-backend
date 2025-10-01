#!/bin/sh
set -e

if [ -n "$GCP_SERVICE_ACCOUNT_JSON_BASE64" ]; then
  # If the value looks like raw JSON (starts with "{"), write it directly.
  if echo "$GCP_SERVICE_ACCOUNT_JSON_BASE64" | head -c 1 | grep -q "{" ; then
    printf '%s' "$GCP_SERVICE_ACCOUNT_JSON_BASE64" > /app/gcp.json
  else
    # Otherwise treat as base64, strip whitespace, then decode.
    CLEAN=$(printf '%s' "$GCP_SERVICE_ACCOUNT_JSON_BASE64" | tr -d '\r\n ')
    echo "$CLEAN" | base64 -d > /app/gcp.json || {
      echo "ERROR: Failed to decode GCP key. Check GCP_SERVICE_ACCOUNT_JSON_BASE64."
      exit 1
    }
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}

