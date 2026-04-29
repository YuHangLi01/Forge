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
git fetch --prune origin main
git reset --hard origin/main

echo "==> [deploy] uv sync"
uv sync --frozen

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
