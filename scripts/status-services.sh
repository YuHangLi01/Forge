#!/usr/bin/env bash
# Quick status check for PostgreSQL, Redis, and ChromaDB.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROMA_PID_FILE="${ROOT}/.chromadb.pid"

ok()   { printf '  \033[32m[OK]\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31m[FAIL]\033[0m %s\n' "$1"; }

echo "PostgreSQL:"
if pg_isready -h localhost -p 5432 -U forge >/dev/null 2>&1; then
    ok "listening on :5432"
else
    fail "not reachable"
fi

echo "Redis:"
if redis-cli -h localhost -p 6379 ping 2>/dev/null | grep -q PONG; then
    ok "PONG on :6379"
else
    fail "not reachable"
fi

echo "ChromaDB:"
if curl -sf http://localhost:8001/api/v2/heartbeat >/dev/null \
   || curl -sf http://localhost:8001/api/v1/heartbeat >/dev/null; then
    ok "heartbeat on :8001"
    if [[ -f "$CHROMA_PID_FILE" ]]; then
        echo "    pid: $(cat "$CHROMA_PID_FILE")"
    fi
else
    fail "not reachable"
fi
