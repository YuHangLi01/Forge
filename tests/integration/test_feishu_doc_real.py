"""Integration test: real Feishu Doc API call via FeishuDocService.

Skipped unless FORGE_RUN_INTEGRATION=1. Requires a real Feishu app with
the docx:document + drive:drive scopes granted, plus reachable network
to open.feishu.cn.

Asserts the round-trip yields a non-empty doc_token and share_url; doesn't
assert content beyond that, since visual quality is checked manually
(see docs/risk-reports/feishu_doc_api_findings.md).
"""

import os
from pathlib import Path

import pytest

from app.services.feishu_doc_service import FeishuDocService

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "meetings" / "01_requirements.md"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("FORGE_RUN_INTEGRATION") != "1",
        reason="FORGE_RUN_INTEGRATION=1 not set; skipping live Feishu Doc call",
    ),
]


@pytest.mark.asyncio
async def test_create_doc_round_trip() -> None:
    md = _FIXTURE.read_text(encoding="utf-8")
    svc = FeishuDocService()
    artifact = await svc.create_from_markdown("forge-integration-test", md)
    assert artifact.doc_id, "doc_token should be populated"
    assert artifact.share_url.startswith("https://"), f"unexpected share_url: {artifact.share_url}"
    # We expect ≥ 1 H1 in the meeting fixture
    assert len(artifact.sections) >= 1
