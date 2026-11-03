#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/scopus_app"
PORT="${PORT:-8080}"
echo "Starting Scopus Scientometrics & Visualization Studio on http://localhost:${PORT} ..."

# Automatically open the browser after 1 second if xdg-open is available
(sleep 1 && command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:${PORT}" >/dev/null 2>&1 || true) &

exec python3 app.py
