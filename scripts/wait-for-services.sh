#!/usr/bin/env bash
# Wait until PostgreSQL, Redis, and ChromaDB are reachable on localhost.
set -euo pipefail

TIMEOUT=${1:-60}
START=$(date +%s)

echo "Waiting for services (timeout ${TIMEOUT}s)..."

wait_for() {
    local name=$1
    local check=$2
    until eval "$check" > /dev/null 2>&1; do
        local now; now=$(date +%s)
        if (( now - START >= TIMEOUT )); then
            echo "TIMEOUT: $name not ready after ${TIMEOUT}s"
            exit 1
        fi
        printf "."
        sleep 2
    done
    echo " [OK] $name"
}

wait_for "PostgreSQL" "pg_isready -h localhost -p 5432 -U forge"
wait_for "Redis" "redis-cli -h localhost -p 6379 ping | grep -q PONG"
wait_for "ChromaDB" "curl -sf http://localhost:8001/api/v2/heartbeat || curl -sf http://localhost:8001/api/v1/heartbeat"

echo "All services ready."
