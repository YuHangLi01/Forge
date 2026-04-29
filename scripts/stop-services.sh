#!/usr/bin/env bash
# Stop locally-running PostgreSQL, Redis, and ChromaDB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROMA_PID_FILE="${ROOT}/.chromadb.pid"

if [[ -f "$CHROMA_PID_FILE" ]]; then
    PID="$(cat "$CHROMA_PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
        echo "==> Stopping ChromaDB (pid $PID)"
        kill "$PID" || true
    fi
    rm -f "$CHROMA_PID_FILE"
fi

echo "==> Stopping Redis"
sudo service redis-server stop || sudo systemctl stop redis-server || true

echo "==> Stopping PostgreSQL"
sudo service postgresql stop || sudo systemctl stop postgresql || true

echo "==> Done."
