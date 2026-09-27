#!/usr/bin/env bash
set -euo pipefail

# Start the upstream Kokoro API locally. WEB_CONCURRENCY=1 is deliberate:
# one A2000 worker owns one model copy and processes one inference at a time.
cd /app
uvicorn api.src.main:app --host 127.0.0.1 --port 8880 &
KOKORO_PID=$!

cleanup() {
  kill "$KOKORO_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

exec python /opt/prepza/worker.py
