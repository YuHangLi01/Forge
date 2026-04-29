#!/usr/bin/env bash
# Start PostgreSQL, Redis, and ChromaDB locally (no Docker).
# ChromaDB runs as a background uv process; PID stored in .chromadb.pid
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROMA_PID_FILE="${ROOT}/.chromadb.pid"
CHROMA_LOG="${ROOT}/.chromadb.log"
CHROMA_DATA="${ROOT}/.chroma_data"

echo "==> Starting PostgreSQL"
sudo service postgresql start || sudo systemctl start postgresql

echo "==> Starting Redis"
sudo service redis-server start || sudo systemctl start redis-server

if [[ -f "$CHROMA_PID_FILE" ]] && kill -0 "$(cat "$CHROMA_PID_FILE")" 2>/dev/null; then
    echo "==> ChromaDB already running (pid $(cat "$CHROMA_PID_FILE"))"
else
    echo "==> Starting ChromaDB on :8001 (logs: .chromadb.log)"
    mkdir -p "$CHROMA_DATA"
    nohup uv run chroma run --host 0.0.0.0 --port 8001 --path "$CHROMA_DATA" \
        > "$CHROMA_LOG" 2>&1 &
    echo $! > "$CHROMA_PID_FILE"
    sleep 2
fi

echo "==> Done. Run 'make services-status' to verify."
