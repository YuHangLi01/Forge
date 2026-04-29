#!/usr/bin/env bash
# Install PostgreSQL 16, Redis 7 on Ubuntu/Debian, and bootstrap the forge DB+user.
# ChromaDB is installed via uv (Python package) and runs in-process, no apt step needed.
set -euo pipefail

if ! command -v sudo >/dev/null; then
    echo "ERROR: sudo is required" >&2
    exit 1
fi

echo "==> apt update + install postgresql redis-server"
sudo apt-get update -y
sudo apt-get install -y postgresql postgresql-contrib redis-server curl

echo "==> Enable & start system services"
sudo service postgresql start || sudo systemctl start postgresql
sudo service redis-server start || sudo systemctl start redis-server

echo "==> Create forge role + database (idempotent)"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='forge'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE ROLE forge LOGIN PASSWORD 'forge' SUPERUSER"

sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='forge'" | grep -q 1 \
    || sudo -u postgres createdb -O forge forge

sudo -u postgres psql -d forge -c "CREATE SCHEMA IF NOT EXISTS forge AUTHORIZATION forge;"
sudo -u postgres psql -d forge -c "CREATE SCHEMA IF NOT EXISTS langgraph AUTHORIZATION forge;"

echo "==> Done. Use 'make services-up' to start, 'make services-status' to verify."
