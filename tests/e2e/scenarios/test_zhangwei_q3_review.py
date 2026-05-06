"""End-to-end scenario: Zhang Wei's 7 personal notes → Q3 review document.

Validates the full RAG pipeline from seeded notes through structure/content gen.
All LLM / Feishu / ChromaDB / Redis calls are mocked — no live infra required.

Run with:
    uv run pytest tests/e2e/scenarios/test_zhangwei_q3_review.py -v --no-cov
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.context_formatter import format_retrieved_context

# ── Fixtures — 7 Zhang Wei notes matching demo_seed.yaml ─────────────────────


def _note(note_id: str, ts: str, text: str, distance: float) -> dict[str, Any]:
    return {
        "text": text,
        "metadata": {
            "source": "demo_seed",
            "note_id": note_id,
            "ts": ts,
            "chunk_type": "user_note",
        },
        "distance": distance,
    }


ZHANGWEI_NOTES: list[dict[str, Any]] = [
    _note(
        "demo_msg_001",
        "2024-07-20T10:15:00+08:00",
        "数据组刚出 Q3 报表，7 月中旬 DAU 出现明显下滑，最低点比 6 月均值低了 18%。"
        "初步看和那次大范围推送通知改版时间吻合，但还没有定论。需要进一步拆分渠道数据。",
        0.05,
    ),
    _note(
        "demo_msg_002",
        "2024-07-25T14:30:00+08:00",
        "和研发核对了一下，7 月 14 日 v3.2.1 发布，同天推送策略切换到了新的「营销通知」模板。"
        "从 Mixpanel 漏斗看，通知到达率没变，但点击率从 12% 掉到了 7%，直接影响了新用户次留。",
        0.07,
    ),
    _note(
        "demo_msg_003",
        "2024-08-02T09:45:00+08:00",
        "用户访谈做了 8 个。普遍反馈新的通知文案太「广告感」，有几个用户直接关闭了通知权限。"
        "老用户影响不大，主要是 7 月新增的这批用户次留很差，7 日留存只有 23%，去年同期是 31%。",
        0.09,
    ),
    _note(
        "demo_msg_004",
        "2024-08-08T16:00:00+08:00",
        "已和设计、运营对齐改版方案：通知文案回归「功能提醒」风格，去掉促销话术；"
        "同时 A/B 测试三套文案，看哪个点击率恢复最快。预计下周三 v3.2.3 上线，观测期 2 周。",
        0.11,
    ),
    _note(
        "demo_msg_005",
        "2024-08-22T11:20:00+08:00",
        "v3.2.3 上线 2 周数据出来了。通知点击率回升到 10.5%，还没完全恢复但趋势正向。"
        "次日留存从最低 19% 回到 26%。A/B 胜出方案是「行动召唤 + 个人化」组合文案，"
        "准备在 Q4 全量推。",
        0.13,
    ),
    _note(
        "demo_msg_006",
        "2024-09-05T10:00:00+08:00",
        "VP 王总在上次一对一提醒：Q3 复盘要重点说明「为什么发版和推送策略没有联动评审」，"
        "这是个流程漏洞。需要在复盘材料里给出改进措施，比如发版前增加推送影响评估环节。",
        0.15,
    ),
    _note(
        "demo_msg_007",
        "2024-09-10T15:30:00+08:00",
        "Q3 整体 DAU 均值比 Q2 低 8%，但 8 月底恢复势头明显，预计 Q4 可以补回来。"
        "核心结论：这次波动是「发版 + 推送策略同步上线，缺乏联动评审」导致的，已有改进措施落地。",
        0.17,
    ),
]


# ── Unit: context formatter ───────────────────────────────────────────────────


def test_format_retrieved_context_includes_all_7_notes() -> None:
    """All 7 notes fit within max_items=5 cap (first 5 are returned)."""
    result = format_retrieved_context(ZHANGWEI_NOTES)
    # default max_items=5
    lines = result.strip().split("\n")
    assert len(lines) == 5
    assert lines[0].startswith("[1]")
    assert "demo_seed" in lines[0]
    assert "2024-07-20" in lines[0]


def test_format_retrieved_context_truncates_text() -> None:
    """Text longer than max_chars is truncated."""
    long_note = [{"text": "A" * 500, "metadata": {"source": "demo_seed"}}]
    result = format_retrieved_context(long_note, max_chars=400)
    assert len(result) < 500


def test_format_retrieved_context_empty_returns_placeholder() -> None:
    assert format_retrieved_context([]) == "（无背景资料）"


def test_format_retrieved_context_missing_metadata() -> None:
    """Chunks without metadata degrade gracefully."""
    chunks = [{"text": "some text"}]
    result = format_retrieved_context(chunks)
    assert "some text" in result
    assert "[1]" in result


def test_format_retrieved_context_labels_source_and_ts() -> None:
    """Label format is '{source} {ts}: {text}'."""
    result = format_retrieved_context(ZHANGWEI_NOTES[:1])
    assert "demo_seed 2024-07-20T10:15:00+08:00:" in result
    assert "7 月中旬" in result


# ── Integration: doc_structure_gen with note context ─────────────────────────


@pytest.mark.asyncio
async def test_doc_structure_gen_uses_full_note_context() -> None:
    """doc_structure_gen passes all 5 note chunks to the LLM prompt (not just top-3 × 150 chars)."""
    from app.schemas.doc_outline import DocOutline, DocOutlineSection
    from app.schemas.enums import OutputFormat, TaskType
    from app.schemas.intent import IntentSchema

    captured_prompt: list[str] = []

    async def _fake_structured(prompt: str, schema: type, **_kwargs: Any) -> Any:
        captured_prompt.append(prompt)
        return DocOutline(
            document_title="Q3产品复盘",
            sections=[
                DocOutlineSection(id="s0", title="背景与数据"),
                DocOutlineSection(id="s1", title="根因分析"),
                DocOutlineSection(id="s2", title="改进措施"),
                DocOutlineSection(id="s3", title="Q4展望"),
            ],
        )

    intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="Q3复盘汇报材料，给VP汇报",
        output_formats=[OutputFormat.document],
        target_audience="VP",
        style_hint="corporate",
        ambiguity_score=0.3,
        missing_info=[],
    )

    state = {
        "task_id": "task-zhangwei-001",
        "user_id": "demo_zhangwei",
        "message_id": "om_zhangwei_001",
        "intent": intent,
        "retrieved_context": ZHANGWEI_NOTES,
    }

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(side_effect=_fake_structured),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.begin_node"),
    ):
        from app.graph.nodes.doc_structure_gen import doc_structure_gen_node

        result = await doc_structure_gen_node(state)

    assert result["doc_outline"]["document_title"] == "Q3产品复盘"
    assert len(result["doc_outline"]["sections"]) >= 4

    # Verify the prompt contains note content — not just first 150 chars of first 3 chunks
    assert len(captured_prompt) == 1
    prompt_text = captured_prompt[0]

    # All 5 notes should appear (formatter uses max_items=5 by default)
    assert "demo_seed" in prompt_text
    assert "v3.2.1" in prompt_text  # from note 2
    assert "用户访谈" in prompt_text  # from note 3

    # Confirm notes-as-material instruction is in prompt
    assert "原始笔记" in prompt_text or "用户素材" in prompt_text


@pytest.mark.asyncio
async def test_doc_content_gen_uses_full_note_context() -> None:
    """doc_content_gen passes all 5 note chunks to each section prompt."""
    from app.schemas.enums import OutputFormat, TaskType
    from app.schemas.intent import IntentSchema

    captured_prompts: list[str] = []

    async def _fake_invoke(prompt: str, **_kwargs: Any) -> str:
        captured_prompts.append(prompt)
        return "本节内容：Q3数据分析显示DAU下滑18%，与v3.2.1发版推送策略同步上线有关。"

    intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="Q3复盘汇报材料",
        output_formats=[OutputFormat.document],
        target_audience="VP",
        style_hint="corporate",
        ambiguity_score=0.3,
        missing_info=[],
    )

    state = {
        "task_id": "task-zhangwei-002",
        "user_id": "demo_zhangwei",
        "message_id": "om_zhangwei_002",
        "intent": intent,
        "retrieved_context": ZHANGWEI_NOTES,
        "doc_outline": {
            "document_title": "Q3产品复盘",
            "sections": [
                {"id": "s0", "title": "背景与数据"},
                {"id": "s1", "title": "根因分析"},
            ],
        },
        "completed_section_ids": [],
    }

    with (
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(side_effect=_fake_invoke),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.begin_node"),
    ):
        from app.graph.nodes.doc_content_gen import doc_content_gen_node

        result = await doc_content_gen_node(state)

    assert len(result["doc"].sections) == 2
    # Each section prompt should contain note context keywords
    for p in captured_prompts:
        assert "demo_seed" in p or "v3.2.1" in p or "用户访谈" in p


# ── Integration: seed_data._seed_notes mock ──────────────────────────────────


@pytest.mark.asyncio
async def test_seed_notes_embeds_and_stores_all_7() -> None:
    """_seed_notes() calls embed_batch once and chroma.add 7 times."""
    from scripts.seed_data import _seed_notes

    mock_chroma = AsyncMock()
    mock_embed = AsyncMock()
    mock_embed.embed_batch = AsyncMock(return_value=[[0.1] * 1024] * 7)

    # Make type assertions pass
    from app.services.chroma_service import ChromaService
    from app.services.embedding_service import EmbeddingService

    mock_chroma.__class__ = ChromaService
    mock_embed.__class__ = EmbeddingService

    notes = [
        {
            "id": f"demo_msg_00{i}",
            "user_id": "demo_zhangwei",
            "ts": "2024-07-20T10:15:00+08:00",
            "channel": "private_to_forge",
            "text": f"Note content {i}",
        }
        for i in range(1, 8)
    ]

    count = await _seed_notes(mock_chroma, mock_embed, notes)

    assert count == 7
    mock_embed.embed_batch.assert_awaited_once()
    assert mock_chroma.add.await_count == 7

    # Verify metadata includes source=demo_seed
    first_call_kwargs = mock_chroma.add.await_args_list[0].kwargs
    assert first_call_kwargs["metadata"]["source"] == "demo_seed"
    assert first_call_kwargs["metadata"]["chunk_type"] == "user_note"
    assert first_call_kwargs["user_id"] == "demo_zhangwei"
