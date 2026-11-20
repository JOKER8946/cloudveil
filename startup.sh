#!/usr/bin/env bash
# Azure App Service startup command: bash startup.sh
# Applies migrations, optionally seeds demo data, then starts gunicorn.
set -euo pipefail

echo "[startup] Applying database migrations..."
flask db upgrade || echo "[startup] WARNING: flask db upgrade failed (no DB yet?)"

echo "[startup] Ensuring seed admin exists..."
flask create-admin || echo "[startup] WARNING: create-admin failed"

if [ "${RUN_SEED:-false}" = "true" ]; then
  echo "[startup] RUN_SEED=true -> seeding demo data..."
  flask seed-demo || echo "[startup] WARNING: seed-demo failed"
fi

echo "[startup] Starting gunicorn..."
exec gunicorn --bind=0.0.0.0 --timeout 600 --workers 2 wsgi:app
