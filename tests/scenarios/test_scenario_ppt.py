"""PPT pipeline scenario tests: ppt_structure_gen → ppt_content_gen → feishu_ppt_write."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.artifacts import PPTArtifact, SlideSchema
from app.schemas.enums import SlideLayout, TaskStatus


def _make_ppt_brief(title: str = "市场分析", slide_count: int = 5) -> dict:
    return {
        "title": title,
        "slide_count": slide_count,
        "audience": "高管",
        "style": "专业简洁",
    }


def _make_raw_slides(n: int = 4) -> list[dict]:
    slides = [
        {
            "slide_index": 0,
            "page_type": "cover",
            "title": "封面",
            "content": {
                "heading": "市场分析报告",
                "subheading": "2026 Q1",
                "speaker_notes": "开场",
            },
        }
    ]
    for i in range(1, n - 1):
        slides.append(
            {
                "slide_index": i,
                "page_type": "content",
                "title": f"第{i}节",
                "content": {
                    "heading": f"章节 {i}",
                    "bullets": [f"要点 {i}.1", f"要点 {i}.2", f"要点 {i}.3"],
                    "speaker_notes": f"备注 {i}",
                },
            }
        )
    slides.append(
        {
            "slide_index": n - 1,
            "page_type": "closing",
            "title": "结尾",
            "content": {
                "heading": "谢谢",
                "subheading": "Q&A",
                "speaker_notes": "结束",
            },
        }
    )
    return slides


def _make_ppt_artifact(title: str = "市场分析报告", n_slides: int = 4) -> PPTArtifact:
    slides = [
        SlideSchema(
            page_index=i,
            layout=SlideLayout.title_content,
            title=f"幻灯片{i + 1}",
            bullets=[f"要点{i + 1}"],
            speaker_notes=f"备注{i + 1}",
        )
        for i in range(n_slides)
    ]
    return PPTArtifact(
        ppt_id="file_token_test",
        title=title,
        slides=slides,
        share_url="https://feishu.test/ppt-001",
    )


@pytest.mark.asyncio
async def test_ppt_pipeline() -> None:
    """Mock LLM + Feishu upload, run full PPT pipeline, assert artifact has ≥3 slides."""
    from app.graph.nodes.feishu_ppt_write import feishu_ppt_write_node
    from app.graph.nodes.ppt_content_gen import ppt_content_gen_node
    from app.graph.nodes.ppt_structure_gen import ppt_structure_gen_node

    raw_slides = _make_raw_slides(4)
    fake_artifact = _make_ppt_artifact(n_slides=4)

    state: dict = {
        "task_id": "task_ppt_test",
        "user_id": "usr_ppt",
        "chat_id": "chat_ppt",
        "message_id": "msg_ppt",
        "normalized_text": "帮我做一份市场分析PPT",
        "completed_steps": [],
        "ppt_brief": None,
        "ppt_slides": [],
        "ppt": None,
        "status": TaskStatus.pending,
        "pending_user_action": None,
    }

    # ── Stage 1: ppt_structure_gen ───────────────────────────────────────────
    from app.schemas.ppt import PPTBriefSchema, SlideBrief

    fake_brief = PPTBriefSchema(
        title="市场分析报告",
        target_audience="高管",
        slides=[
            SlideBrief(slide_index=0, page_type="cover", title="封面"),
            SlideBrief(slide_index=1, page_type="content", title="市场现状"),
            SlideBrief(slide_index=2, page_type="content", title="竞争分析"),
            SlideBrief(slide_index=3, page_type="closing", title="结论"),
        ],
    )
    with patch(
        "app.services.llm_service.LLMService.structured", new_callable=AsyncMock
    ) as mock_llm:
        mock_llm.return_value = fake_brief
        result1 = await ppt_structure_gen_node(state)

    assert "ppt_brief" in result1
    assert result1["ppt_brief"]["title"] == "市场分析报告"
    state.update(result1)
    state["completed_steps"] = list(state.get("completed_steps", [])) + ["ppt_structure_gen"]

    # ── Stage 2: ppt_content_gen ─────────────────────────────────────────────
    import json as _json

    slide_dicts = [
        {
            "slide_index": s["slide_index"],
            "page_type": s["page_type"],
            "title": s["title"],
            "content": {
                "heading": s["content"]["heading"],
                "bullets": s["content"].get("bullets", []),
                "speaker_notes": "备注",
            },
        }
        for s in raw_slides
    ]
    fake_slides_response = _json.dumps({"slides": slide_dicts})

    with (
        patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster",
            return_value=MagicMock(begin_node=MagicMock(), emit_progress=MagicMock()),
        ),
    ):
        mock_llm.return_value = fake_slides_response
        result2 = await ppt_content_gen_node(state)

    assert "ppt_slides" in result2
    assert len(result2["ppt_slides"]) >= 3
    state.update(result2)
    state["completed_steps"] = list(state.get("completed_steps", [])) + ["ppt_content_gen"]

    # ── Stage 3: feishu_ppt_write ────────────────────────────────────────────
    with (
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new_callable=AsyncMock,
            return_value=fake_artifact,
        ),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter",
            return_value=AsyncMock(),
        ),
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster",
            return_value=MagicMock(emit_artifact=MagicMock()),
        ),
        patch("redis.asyncio.from_url") as mock_redis,
    ):
        mock_redis.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(setex=AsyncMock()))
        mock_redis.return_value.__aexit__ = AsyncMock(return_value=False)
        result3 = await feishu_ppt_write_node(state)

    assert result3["status"] == TaskStatus.completed
    assert result3["ppt"].ppt_id == "file_token_test"
    assert len(result3["ppt"].slides) >= 3
    assert result3["ppt"].share_url == "https://feishu.test/ppt-001"


@pytest.mark.asyncio
async def test_ppt_slide_editor() -> None:
    """Test ppt_slide_editor: modifies target slide and re-uploads."""
    from app.graph.nodes.ppt_slide_editor import ppt_slide_editor_node
    from app.schemas.intent import ModificationIntent

    existing_artifact = _make_ppt_artifact(n_slides=4)
    new_artifact = _make_ppt_artifact(n_slides=4)
    new_artifact.slides[1] = SlideSchema(
        page_index=1,
        layout=SlideLayout.title_content,
        title="Modified Slide",
        bullets=["Updated bullet"],
        speaker_notes="Updated notes",
    )

    mod_intent = ModificationIntent(
        target="presentation",
        scope_type="specific_slide",
        scope_identifier="第2页",
        modification_type="rewrite",
        instruction="请改成英文",
    )

    state: dict = {
        "task_id": "task_edit_ppt",
        "user_id": "usr_edit",
        "chat_id": "chat_edit",
        "message_id": "msg_edit",
        "ppt": existing_artifact,
        "mod_intent": mod_intent,
        "modification_history": [],
        "completed_steps": [],
        "pending_user_action": None,
    }

    fake_llm_response = '{"heading": "Modified Slide", "bullets": ["Updated bullet"], "speaker_notes": "Updated notes"}'  # noqa: E501

    with (
        patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new_callable=AsyncMock,
            return_value=new_artifact,
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=AsyncMock()),
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster",
            return_value=MagicMock(emit_artifact=MagicMock()),
        ),
        patch("redis.asyncio.from_url") as mock_redis,
    ):
        mock_llm.return_value = fake_llm_response
        mock_redis.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(setex=AsyncMock()))
        mock_redis.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await ppt_slide_editor_node(state)

    assert result["status"] == TaskStatus.completed
    assert len(result["modification_history"]) == 1
    assert result["modification_history"][0].scope_identifier == "第2页"
