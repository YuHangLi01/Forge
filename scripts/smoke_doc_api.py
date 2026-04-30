"""Smoke test: create a Feishu Doc from a markdown fixture using FeishuDocService.

Calls live Feishu OpenAPI. Requires real FEISHU_APP_ID / FEISHU_APP_SECRET
in `.env` and the `docx:document` + `drive:drive` scopes granted on the
app. Run on the server (or any host with valid creds) — not gated by env
vars because the script is invoked manually.

Usage:
    uv run python scripts/smoke_doc_api.py [markdown-path] [--folder-token TOKEN]

If markdown-path is omitted, defaults to the first meeting fixture.
The script prints doc_token, share_url, block_count, and end-to-end ms.
Exit 0 on success, 1 on Feishu API failure.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.services.feishu_doc_service import FeishuDocService  # noqa: E402

_DEFAULT_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "meetings" / "01_requirements.md"


async def _main(md_path: Path, folder_token: str) -> int:
    if not md_path.exists():
        print(f"markdown file not found: {md_path}", file=sys.stderr)
        return 1
    markdown = md_path.read_text(encoding="utf-8")
    title = md_path.stem.replace("_", " ")

    svc = FeishuDocService()
    started = time.perf_counter()
    try:
        artifact = await svc.create_from_markdown(title, markdown, folder_token=folder_token)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"FAILED after {elapsed_ms:.0f} ms: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"doc_id:     {artifact.doc_id}")
    print(f"title:      {artifact.title}")
    print(f"share_url:  {artifact.share_url}")
    print(f"sections:   {len(artifact.sections)}")
    print(f"latency_ms: {elapsed_ms:.0f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown", nargs="?", type=Path, default=_DEFAULT_FIXTURE)
    ap.add_argument("--folder-token", default="", help="Feishu Drive folder to create the doc in")
    args = ap.parse_args()
    return asyncio.run(_main(args.markdown, args.folder_token))


if __name__ == "__main__":
    sys.exit(main())
