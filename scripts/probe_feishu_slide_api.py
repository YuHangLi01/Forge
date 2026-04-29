"""Probe Feishu native Slides API capabilities.

Walks 10 candidate operations against the Feishu Slides API
(`/open-apis/slides/v1`), logging result/error/latency for each. Output
is a JSON report at out/probe/feishu_slide_api_<timestamp>.json that the
strategy decision document (`docs/risk-reports/ppt_strategy_decision.md`)
references.

Why it's a probe, not a service:
- Feishu Slides API is younger than Doc API and surface coverage is less
  documented; we want hard evidence (HTTP status, error code, latency)
  rather than relying on docs.
- Decisions about whether to ship a `FeishuSlidesService` (option A) vs
  the python-pptx + Drive upload path (option B, default) hinge on what
  this probe finds.

Run on the server (or any host with valid creds + slides:slides scope).
NOT gated by FORGE_RUN_INTEGRATION because it's invoked manually.

Usage:
    uv run python scripts/probe_feishu_slide_api.py [--folder-token TOKEN]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.config import get_settings  # noqa: E402

logger = structlog.get_logger(__name__)

_OUT_DIR = _REPO_ROOT / "out" / "probe"


async def _get_tenant_token(client: httpx.AsyncClient, settings: object) -> str:
    url = f"{settings.FEISHU_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal"  # type: ignore[attr-defined]
    resp = await client.post(
        url,
        json={
            "app_id": settings.FEISHU_APP_ID,  # type: ignore[attr-defined]
            "app_secret": settings.FEISHU_APP_SECRET,  # type: ignore[attr-defined]
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"tenant_access_token: {data}")
    return str(data["tenant_access_token"])


async def _try(
    client: httpx.AsyncClient,
    name: str,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make one probe call and return a structured row for the report."""
    started = time.perf_counter()
    try:
        resp = await client.request(method, url, headers=headers, json=json_body, timeout=10.0)
        elapsed_ms = (time.perf_counter() - started) * 1000
        body: Any = None
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:200]
        return {
            "op": name,
            "http_status": resp.status_code,
            "feishu_code": body.get("code") if isinstance(body, dict) else None,
            "feishu_msg": body.get("msg") if isinstance(body, dict) else None,
            "latency_ms": round(elapsed_ms, 0),
            "ok": resp.status_code == 200
            and (isinstance(body, dict) and body.get("code") in (0, None)),
            "body_excerpt": str(body)[:300],
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "op": name,
            "http_status": None,
            "feishu_code": None,
            "feishu_msg": None,
            "latency_ms": round(elapsed_ms, 0),
            "ok": False,
            "error": repr(exc)[:300],
        }


async def _probe_all(folder_token: str) -> dict[str, Any]:
    settings = get_settings()
    domain = settings.FEISHU_DOMAIN.rstrip("/")
    rows: list[dict[str, Any]] = []
    deck_token: str | None = None
    page_id: str | None = None

    async with httpx.AsyncClient() as client:
        token = await _get_tenant_token(client, settings)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        # 1. Create a new deck
        body: dict[str, Any] = {"title": "forge-probe-deck"}
        if folder_token:
            body["folder_token"] = folder_token
        row = await _try(
            client,
            "create_deck",
            "POST",
            f"{domain}/open-apis/slides/v1/presentations",
            headers,
            body,
        )
        rows.append(row)
        if row.get("ok"):
            try:
                excerpt = row["body_excerpt"]
                data = json.loads(excerpt) if isinstance(excerpt, str) else None
                if data and isinstance(data.get("data"), dict):
                    deck_token = data["data"].get("presentation_token")
            except Exception:
                pass

        # If create failed, the rest is moot — record skipped rows for reference
        if not deck_token:
            for op in (
                "list_layouts",
                "add_page",
                "set_title",
                "set_bullets",
                "insert_image",
                "insert_chart",
                "patch_page",
                "delete_page",
                "get_share_url",
            ):
                rows.append({"op": op, "skipped": "create_deck failed", "ok": False})
            return {"rows": rows, "deck_token": None}

        # 2. List layouts of the new deck
        rows.append(
            await _try(
                client,
                "list_layouts",
                "GET",
                f"{domain}/open-apis/slides/v1/presentations/{deck_token}/layouts",
                headers,
            )
        )

        # 3. Add a page (best-effort — actual API path may differ)
        row = await _try(
            client,
            "add_page",
            "POST",
            f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages",
            headers,
            {"title": "probe page 1"},
        )
        rows.append(row)
        if row.get("ok"):
            try:
                excerpt = row["body_excerpt"]
                data = json.loads(excerpt) if isinstance(excerpt, str) else None
                if data and isinstance(data.get("data"), dict):
                    page_id = (data["data"].get("page") or {}).get("page_id")
            except Exception:
                pass

        # 4-7. operations that need a page_id
        if page_id:
            rows.append(
                await _try(
                    client,
                    "set_title",
                    "PATCH",
                    f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages/{page_id}",
                    headers,
                    {"title": "probe title set"},
                )
            )
            rows.append(
                await _try(
                    client,
                    "set_bullets",
                    "PATCH",
                    f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages/{page_id}/elements",
                    headers,
                    {"bullets": ["a", "b", "c"]},
                )
            )
            rows.append(
                await _try(
                    client,
                    "insert_image",
                    "POST",
                    f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages/{page_id}/images",
                    headers,
                    {"image_token": "fake"},
                )
            )
            rows.append(
                await _try(
                    client,
                    "insert_chart",
                    "POST",
                    f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages/{page_id}/charts",
                    headers,
                    {"chart_type": "bar"},
                )
            )
            rows.append(
                await _try(
                    client,
                    "patch_page",
                    "PATCH",
                    f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages/{page_id}",
                    headers,
                    {"layout": "title_content"},
                )
            )
            rows.append(
                await _try(
                    client,
                    "delete_page",
                    "DELETE",
                    f"{domain}/open-apis/slides/v1/presentations/{deck_token}/pages/{page_id}",
                    headers,
                )
            )
        else:
            for op in (
                "set_title",
                "set_bullets",
                "insert_image",
                "insert_chart",
                "patch_page",
                "delete_page",
            ):
                rows.append({"op": op, "skipped": "add_page failed / no page_id", "ok": False})

        # 8. Share URL
        rows.append(
            await _try(
                client,
                "get_share_url",
                "GET",
                f"{domain}/open-apis/drive/v1/files/{deck_token}",
                headers,
            )
        )

    return {"rows": rows, "deck_token": deck_token}


def _summarize(report: dict[str, Any]) -> str:
    lines = [f"deck_token: {report.get('deck_token')}"]
    lines.append(f"{'op':<20s}  {'http':>4s}  {'feishu':>6s}  {'ms':>6s}  ok")
    for r in report["rows"]:
        if "skipped" in r:
            lines.append(f"{r['op']:<20s}  ----  ------  ------  SKIP ({r['skipped']})")
            continue
        lines.append(
            f"{r['op']:<20s}  {str(r.get('http_status') or '-'):>4s}  "
            f"{str(r.get('feishu_code') or '-'):>6s}  "
            f"{str(r.get('latency_ms') or '-'):>6s}  "
            f"{'OK' if r.get('ok') else 'FAIL'}"
        )
    return "\n".join(lines)


async def _main(folder_token: str) -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"probing Feishu Slides API; results will be saved under {_OUT_DIR}")
    report = await _probe_all(folder_token)
    print(_summarize(report))

    out_path = _OUT_DIR / f"feishu_slide_api_{int(time.time())}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nfull report: {out_path}")
    return 0 if any(r.get("ok") for r in report["rows"]) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder-token", default="", help="Feishu Drive folder for the probe deck")
    args = ap.parse_args()
    return asyncio.run(_main(args.folder_token))


if __name__ == "__main__":
    sys.exit(main())
