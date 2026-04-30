"""Smoke test: build a demo Doc + PPT and (optionally) upload to Feishu.

Two modes:
- Default (offline): build .pptx bytes locally, write to disk, exercise
  the pipeline up to the upload boundary. Useful in CI as a build check.
- ``--live``: call the real Feishu OpenAPI via FeishuAdapter — creates a
  Doc, builds and uploads the PPT, prints share URLs. Requires valid
  FEISHU_APP_ID / FEISHU_APP_SECRET in .env.

Usage:
    uv run python scripts/smoke_demo_pipeline.py [fixture] [--live]

`fixture` defaults to "01_requirements"; pass any of the 5 fixture names.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.services.ppt_outline_loader import load_outline  # noqa: E402
from app.services.ppt_service import PPTService  # noqa: E402
from app.tasks.demo_tasks import _FIXTURE_NAMES, _FIXTURE_TITLES  # noqa: E402

_MEETINGS_DIR = _REPO_ROOT / "tests" / "fixtures" / "meetings"
_OUTLINES_DIR = _REPO_ROOT / "tests" / "fixtures" / "outlines"


async def _offline(fixture: str, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    title = _FIXTURE_TITLES[fixture]
    print(f"[offline] fixture={fixture} title={title}")
    started = time.perf_counter()

    md_path = _MEETINGS_DIR / f"{fixture}.md"
    print(f"  doc: {md_path.name} ({md_path.stat().st_size:,} bytes)")

    outline_title, subtitle, slides = load_outline(_OUTLINES_DIR / f"{fixture}.json")
    pptx_bytes = await PPTService().build_pptx_bytes(outline_title, slides, subtitle=subtitle)

    out_path = out_dir / f"{fixture}.pptx"
    out_path.write_bytes(pptx_bytes)
    print(f"  pptx: {out_path} ({len(pptx_bytes):,} bytes)")

    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"  total: {elapsed_ms:.0f} ms")
    return 0


async def _live(fixture: str) -> int:
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.tasks.demo_tasks import _build_demo

    feishu = FeishuAdapter()
    title_zh = _FIXTURE_TITLES[fixture]
    print(f"[live] fixture={fixture} title={title_zh}")
    started = time.perf_counter()
    try:
        result = await _build_demo(feishu, fixture, title_zh)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"FAILED after {elapsed_ms:.0f} ms: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"  doc:  {result['doc_share_url']}")
    print(f"  pptx: {result['pptx_share_url']}")
    print(f"  total: {elapsed_ms:.0f} ms")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture", nargs="?", default="01_requirements", choices=_FIXTURE_NAMES)
    ap.add_argument("--live", action="store_true", help="hit real Feishu APIs")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_REPO_ROOT / "out" / "demo",
        help="where to write .pptx in offline mode",
    )
    args = ap.parse_args()
    if args.live:
        return asyncio.run(_live(args.fixture))
    return asyncio.run(_offline(args.fixture, args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
