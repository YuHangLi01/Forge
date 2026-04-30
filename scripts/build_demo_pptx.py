"""Smoke + demo: build the five Stage 1 demo .pptx decks from outline fixtures.

Reads tests/fixtures/outlines/*.json and produces matching .pptx files
under out/pptx/. Intentionally offline — no Feishu / Doubao calls — so it
can be run in CI as a build verification.

Usage:
    uv run python scripts/build_demo_pptx.py [--out-dir out/pptx]
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Ensure repo root is on PYTHONPATH when invoked as a script
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.services.ppt_outline_loader import load_outline  # noqa: E402
from app.services.ppt_service import PPTService  # noqa: E402

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "outlines"


async def _build_one(svc: PPTService, fixture: Path, out_dir: Path) -> tuple[Path, int, float]:
    started = time.perf_counter()
    title, subtitle, slides = load_outline(fixture)
    pptx_bytes = await svc.build_pptx_bytes(title, slides, subtitle=subtitle)
    out_path = out_dir / f"{fixture.stem}.pptx"
    out_path.write_bytes(pptx_bytes)
    return out_path, len(pptx_bytes), (time.perf_counter() - started) * 1000


async def _main(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    fixtures = sorted(_FIXTURE_DIR.glob("*.json"))
    if not fixtures:
        print(f"no fixtures found under {_FIXTURE_DIR}", file=sys.stderr)
        return 1

    svc = PPTService()
    print(f"building {len(fixtures)} decks → {out_dir}")
    total_bytes = 0
    for fx in fixtures:
        path, size, ms = await _build_one(svc, fx, out_dir)
        total_bytes += size
        print(f"  ✓ {path.name:35s}  {size:>7,d} bytes  {ms:>6.0f} ms")
    print(f"done: {total_bytes:,} bytes total")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "out" / "pptx",
        help="where to write .pptx files (default: out/pptx)",
    )
    args = ap.parse_args()
    return asyncio.run(_main(args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
