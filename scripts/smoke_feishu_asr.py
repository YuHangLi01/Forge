"""Smoke test: invoke FeishuASRClient against the real Feishu STT API.

Usage:
    uv run python scripts/smoke_feishu_asr.py [audio-file-path]

Defaults to tests/fixtures/sample_voice.wav. Replace with a real voice
recording to validate end-to-end transcription quality.

Exit codes:
    0  API call succeeded; recognition_text printed (may be empty for
       synthetic audio — that's expected)
    1  API call raised or recognition_text was unexpectedly None
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from app.integrations.feishu_asr.client import FeishuASRClient

_DEFAULT_FIXTURE = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "sample_voice.wav"
)


async def _main(path: Path, fmt: str) -> int:
    if not path.exists():
        print(f"audio file not found: {path}", file=sys.stderr)
        return 1
    audio = path.read_bytes()
    print(f"audio: {path} ({len(audio)} bytes, format={fmt})")

    client = FeishuASRClient()
    started = time.perf_counter()
    try:
        text = await client.transcribe(audio, audio_format=fmt)
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"FAILED after {elapsed_ms:.0f} ms: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"recognition_text: {text!r}")
    print(f"latency_ms: {elapsed_ms:.0f}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    path = Path(args[0]) if args else _DEFAULT_FIXTURE
    fmt = os.getenv("FEISHU_ASR_FORMAT", path.suffix.lstrip(".") or "wav")
    return asyncio.run(_main(path, fmt))


if __name__ == "__main__":
    sys.exit(main())
