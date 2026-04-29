"""Integration test: real Feishu STT API call.

Skipped unless FORGE_RUN_INTEGRATION=1 is set in the environment.
Requires real FEISHU_APP_ID / FEISHU_APP_SECRET in `.env` and the
`speech_to_text:speech` scope granted on the Feishu app.

The shipped fixture (`tests/fixtures/sample_voice.wav`) is a synthetic
sine wave, so Feishu won't recognise meaningful Chinese — the test only
asserts that the API call succeeds (returns a string, possibly empty).
For semantic-quality checks, replace the fixture with a real recording
or run `scripts/smoke_feishu_asr.py <your-voice.wav>`.
"""

import os
from pathlib import Path

import pytest

from app.integrations.feishu_asr.client import FeishuASRClient

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample_voice.wav"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("FORGE_RUN_INTEGRATION") != "1",
        reason="FORGE_RUN_INTEGRATION=1 not set; skipping live Feishu STT call",
    ),
]


@pytest.mark.asyncio
async def test_feishu_stt_real_api_returns_string() -> None:
    audio = _FIXTURE.read_bytes()
    assert audio, "fixture is empty — regenerate tests/fixtures/sample_voice.wav"

    client = FeishuASRClient()
    text = await client.transcribe(audio, audio_format="wav")
    # Don't assert on content — sine wave fixture won't transcribe to real
    # speech. The point is: API call round-trips and returns a string.
    assert isinstance(text, str)
