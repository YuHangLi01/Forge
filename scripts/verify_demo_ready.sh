#!/usr/bin/env bash
# verify_demo_ready.sh — pre-demo readiness check
# Exit 0 = all systems go; exit 1 = something is broken.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Forge Demo Readiness Check ==="
echo ""

FAILED=0

# ── 1. Infra: PostgreSQL / Redis / ChromaDB ──────────────────────────────────
echo ">>> [1/4] Infrastructure connectivity..."
if uv run python scripts/smoke-infra.py; then
    echo "[PASS] Infrastructure OK"
else
    echo "[FAIL] Infrastructure check failed"
    FAILED=1
fi
echo ""

# ── 2. Feishu API reachability ────────────────────────────────────────────────
echo ">>> [2/4] Feishu API token..."
if uv run python - <<'PY'
import asyncio, os, sys
async def main():
    from app.integrations.feishu.adapter import FeishuAdapter
    try:
        adapter = FeishuAdapter()
        token = await adapter._get_tenant_access_token()
        assert token, "empty token"
        print("[OK] Feishu tenant_access_token obtained")
    except Exception as e:
        print(f"[FAIL] Feishu: {e}", file=sys.stderr)
        sys.exit(1)
asyncio.run(main())
PY
then
    echo "[PASS] Feishu OK"
else
    echo "[FAIL] Feishu API unreachable"
    FAILED=1
fi
echo ""

# ── 3. Ruff + mypy ────────────────────────────────────────────────────────────
echo ">>> [3/4] Static analysis..."
if uv run ruff check . && uv run mypy app/ --ignore-missing-imports --no-error-summary; then
    echo "[PASS] Lint + type check OK"
else
    echo "[FAIL] Static analysis errors"
    FAILED=1
fi
echo ""

# ── 4. Test suite ─────────────────────────────────────────────────────────────
echo ">>> [4/4] Test suite..."
if uv run pytest --no-cov -q --tb=no -q 2>&1 | tail -3; then
    echo "[PASS] Tests OK"
else
    echo "[FAIL] Test failures detected"
    FAILED=1
fi
echo ""

# ── Summary ──────────────────────────────────────────────────────────────────
if [[ $FAILED -eq 0 ]]; then
    echo "✅  All checks passed — demo environment is ready."
    exit 0
else
    echo "❌  One or more checks failed — fix before demo."
    exit 1
fi
