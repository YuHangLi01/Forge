#!/usr/bin/env bash
# Server-side deploy script. Run by GitHub Actions over SSH.
# Pre-reqs on server:
#   - repo cloned to /opt/forge, owned by deploy user
#   - .env populated at /opt/forge/.env
#   - uv installed for the deploy user (~/.local/bin/uv)
#   - systemd units forge-api.service / forge-worker.service installed
#   - deploy user has NOPASSWD sudo for: systemctl restart forge-api forge-worker
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_DIR="/opt/forge"
HEALTH_URL="http://127.0.0.1:8000/healthz"

cd "$REPO_DIR"

echo "==> [deploy] git fetch + reset to origin/main"
# Aliyun ↔ github.com TLS sometimes gets reset mid-handshake
# (GnuTLS recv error -110); retry up to 3× with backoff.
for attempt in 1 2 3; do
  if git fetch --prune origin main; then
    break
  fi
  if [ "$attempt" -eq 3 ]; then
    echo "==> [deploy] git fetch failed after 3 attempts" >&2
    exit 1
  fi
  echo "==> [deploy] git fetch attempt $attempt failed, retrying in $((attempt * 5))s…" >&2
  sleep $((attempt * 5))
done
git reset --hard origin/main

echo "==> [deploy] removing stale venv to avoid cross-user ownership conflicts"
rm -rf .venv

echo "==> [deploy] uv sync (skipping ml extras — sentence-transformers/torch not needed on API/worker)"
uv sync --frozen --no-extra ml

echo "==> [deploy] alembic upgrade head"
uv run alembic upgrade head

echo "==> [deploy] systemctl restart forge-api forge-worker"
sudo systemctl restart forge-api
sudo systemctl restart forge-worker

echo "==> [deploy] health check"
for i in 1 2 3 4 5; do
  sleep 2
  if curl --fail --silent --show-error "$HEALTH_URL" >/dev/null; then
    echo "==> [deploy] healthz OK"
    exit 0
  fi
done

echo "==> [deploy] healthz FAILED" >&2
sudo journalctl -u forge-api -n 50 --no-pager >&2 || true
exit 1
