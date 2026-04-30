"""Integration test: end-to-end demo pipeline against real Feishu.

Skipped unless FORGE_RUN_INTEGRATION=1. Requires:
- FEISHU_APP_ID / FEISHU_APP_SECRET in .env
- Scopes: docx:document, drive:drive (or drive:file:upload), im:message
- App published to a tenant where the credential set has Drive write access

Asserts the pipeline returns non-empty Doc + PPT tokens and share URLs.
"""

import os

import pytest

from app.integrations.feishu.adapter import FeishuAdapter
from app.tasks.demo_tasks import _build_demo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("FORGE_RUN_INTEGRATION") != "1",
        reason="FORGE_RUN_INTEGRATION=1 not set; skipping live demo pipeline",
    ),
]


@pytest.mark.asyncio
async def test_demo_pipeline_round_trip() -> None:
    feishu = FeishuAdapter()
    result = await _build_demo(feishu, "01_requirements", "需求确定会会议纪要")
    assert result["doc_token"], "Feishu Doc token should not be empty"
    assert result["pptx_token"], "Drive file token should not be empty"
    assert result["doc_share_url"].startswith("https://")
    assert result["pptx_share_url"].startswith("https://")
