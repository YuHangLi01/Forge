"""Tests for T11 doc nodes: doc_structure_gen, doc_content_gen, feishu_doc_write,
mod_intent_parser, doc_section_editor — including the Scenario C modification chain."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.doc_content_gen import doc_content_gen_node
from app.graph.nodes.doc_section_editor import doc_section_editor_node
from app.graph.nodes.doc_structure_gen import doc_structure_gen_node
from app.graph.nodes.feishu_doc_write import feishu_doc_write_node
from app.graph.nodes.mod_intent_parser import mod_intent_parser_node
from app.schemas.artifacts import DocArtifact, DocSection
from app.schemas.doc_outline import DocOutline, DocOutlineSection
from app.schemas.intent import ModificationIntent
from app.schemas.modification import ModificationRecord


def _intent_mock(goal: str = "写一份复盘文档") -> MagicMock:
    m = MagicMock()
    m.primary_goal = goal
    m.target_audience = "高管"
    m.style_hint = "简洁"
    m.output_formats = ["document"]
    return m


def _make_doc(sections: list[tuple[str, str, list[str]]] | None = None) -> DocArtifact:
    if sections is None:
        sections = [("背景", "背景内容", ["blk-001", "blk-002"]), ("数据分析", "数据内容", [])]
    return DocArtifact(
        doc_id="doc-001",
        title="Q3复盘",
        sections=[
            DocSection(id=f"s{i}", title=t, content_md=c, block_ids=blks)
            for i, (t, c, blks) in enumerate(sections)
        ],
        share_url="https://feishu.cn/doc/doc-001",
    )


# ── doc_structure_gen ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_doc_structure_gen_returns_outline() -> None:
    outline = DocOutline(
        document_title="Q3复盘",
        sections=[
            DocOutlineSection(id="s0", title="背景"),
            DocOutlineSection(id="s1", title="数据分析"),
            DocOutlineSection(id="s2", title="结论"),
        ],
    )
    state = {"intent": _intent_mock(), "retrieved_context": []}

    with patch(
        "app.services.llm_service.LLMService.structured",
        new=AsyncMock(return_value=outline),
    ):
        result = await doc_structure_gen_node(state)

    assert result["doc_outline"]["document_title"] == "Q3复盘"
    assert len(result["doc_outline"]["sections"]) == 3


@pytest.mark.asyncio
async def test_doc_structure_gen_fallback_on_llm_error() -> None:
    state = {"intent": _intent_mock(), "retrieved_context": []}

    with patch(
        "app.services.llm_service.LLMService.structured",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        result = await doc_structure_gen_node(state)

    assert "doc_outline" in result
    assert len(result["doc_outline"]["sections"]) >= 3


# ── doc_content_gen ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_doc_content_gen_generates_all_sections() -> None:
    state = {
        "intent": _intent_mock(),
        "retrieved_context": [],
        "completed_section_ids": [],
        "doc_outline": {
            "document_title": "Q3复盘",
            "sections": [{"id": "s0", "title": "背景"}, {"id": "s1", "title": "数据"}],
        },
    }

    with patch(
        "app.services.llm_service.LLMService.invoke", new=AsyncMock(return_value="正文内容")
    ):
        result = await doc_content_gen_node(state)

    doc: DocArtifact = result["doc"]
    assert len(doc.sections) == 2
    assert doc.sections[0].content_md == "正文内容"
    assert "背景" in result["doc_markdown"]


@pytest.mark.asyncio
async def test_doc_content_gen_skips_completed_sections() -> None:
    existing_doc = DocArtifact(
        doc_id="",
        title="Q3",
        sections=[DocSection(id="s0", title="背景", content_md="已有内容")],
    )
    state = {
        "intent": _intent_mock(),
        "retrieved_context": [],
        "completed_section_ids": ["s0"],
        "doc": existing_doc,
        "doc_outline": {
            "document_title": "Q3",
            "sections": [{"id": "s0", "title": "背景"}],
        },
    }

    with patch("app.services.llm_service.LLMService.invoke", new=AsyncMock()) as mock_llm:
        result = await doc_content_gen_node(state)

    mock_llm.assert_not_awaited()
    assert result["doc"].sections[0].content_md == "已有内容"


# ── feishu_doc_write ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feishu_doc_write_calls_service() -> None:
    in_mem_doc = DocArtifact(
        doc_id="",
        title="Q3复盘",
        sections=[DocSection(id="s0", title="背景", content_md="内容")],
    )
    written_doc = DocArtifact(
        doc_id="real-doc-123",
        title="Q3复盘",
        sections=[DocSection(id="s0", title="背景", content_md="内容", block_ids=["blk1"])],
        share_url="https://feishu.cn/doc/real-doc-123",
    )
    state = {"doc": in_mem_doc, "doc_markdown": "# 背景\n\n内容"}

    with (
        patch("app.integrations.feishu.adapter.FeishuAdapter"),
        patch(
            "app.services.feishu_doc_service.FeishuDocService.create_from_markdown",
            new=AsyncMock(return_value=written_doc),
        ),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.set_permission_public",
            new=AsyncMock(),
        ),
    ):
        result = await feishu_doc_write_node(state)

    assert result["doc"].doc_id == "real-doc-123"
    assert result["doc"].share_url != ""


# ── mod_intent_parser ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mod_intent_parser_returns_intent() -> None:
    mod = ModificationIntent(
        target="document",
        scope_type="specific_section",
        scope_identifier="数据分析",
        modification_type="rewrite",
        instruction="简化数据分析一节",
    )
    state = {"normalized_text": "把数据分析那节改简洁", "doc": _make_doc()}

    with patch("app.services.llm_service.LLMService.structured", new=AsyncMock(return_value=mod)):
        result = await mod_intent_parser_node(state)

    assert result["mod_intent"].scope_identifier == "数据分析"


@pytest.mark.asyncio
async def test_mod_intent_parser_returns_failed_on_llm_error() -> None:
    """On LLM failure mod_intent_parser emits error and returns failed status (no fallback)."""
    state = {"normalized_text": "改一改", "doc": _make_doc(), "message_id": ""}

    with patch(
        "app.services.llm_service.LLMService.structured",
        new=AsyncMock(side_effect=RuntimeError("network error")),
    ):
        result = await mod_intent_parser_node(state)

    assert result.get("status") == "failed"
    assert "mod_intent" not in result


# ── doc_section_editor (Scenario C) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_doc_section_editor_updates_content_and_records_history() -> None:
    doc = _make_doc([("背景", "原始背景内容", []), ("数据分析", "原始数据内容", [])])
    mod = ModificationIntent(
        target="document",
        scope_type="specific_section",
        scope_identifier="数据分析",
        modification_type="rewrite",
        instruction="把数据分析简化",
    )
    state = {
        "doc": doc,
        "mod_intent": mod,
        "modification_history": [],
    }

    with patch(
        "app.services.llm_service.LLMService.invoke", new=AsyncMock(return_value="简化后的数据分析")
    ):
        result = await doc_section_editor_node(state)

    updated_doc: DocArtifact = result["doc"]
    assert updated_doc.sections[1].content_md == "简化后的数据分析"
    assert len(result["modification_history"]) == 1
    record: ModificationRecord = result["modification_history"][0]
    assert record.scope_identifier == "数据分析"
    assert "原始数据内容" in record.before_summary
    assert result["mod_intent"] is None  # cleared


@pytest.mark.asyncio
async def test_scenario_c_full_modification_chain() -> None:
    """Scenario C: create doc → modify section 2 → reference prior change."""
    # Step A: initial doc (already written to Feishu in prior graph run)
    doc = _make_doc(
        [
            ("概述", "概述内容", []),
            ("数据分析", "初始数据内容，含DAU数据", []),
            ("结论", "结论内容", []),
        ]
    )

    # Step B: "把第2节改简洁"
    mod_b = ModificationIntent(
        target="document",
        scope_type="specific_section",
        scope_identifier="数据分析",
        modification_type="rewrite",
        instruction="简化数据分析，突出关键指标",
    )
    state_b = {"doc": doc, "mod_intent": mod_b, "modification_history": []}

    with patch(
        "app.services.llm_service.LLMService.invoke",
        new=AsyncMock(return_value="简化后的数据分析，DAU环比+12%"),
    ):
        result_b = await doc_section_editor_node(state_b)

    doc_after_b: DocArtifact = result_b["doc"]
    history_b: list[ModificationRecord] = result_b["modification_history"]
    assert len(history_b) == 1
    assert history_b[0].scope_identifier == "数据分析"
    assert "DAU" in doc_after_b.sections[1].content_md

    # Step C: "刚才改的那段加上数据来源" — mod_intent_parser uses history to resolve scope
    mod_c = ModificationIntent(
        target="document",
        scope_type="specific_section",
        scope_identifier="数据分析",  # resolved by mod_intent_parser using history
        modification_type="append",
        instruction="在数据分析末尾追加数据来源说明",
    )
    state_c = {"doc": doc_after_b, "mod_intent": mod_c, "modification_history": history_b}

    with patch(
        "app.services.llm_service.LLMService.invoke",
        new=AsyncMock(return_value="简化后的数据分析，DAU环比+12%\n\n数据来源：内部BI系统"),
    ):
        result_c = await doc_section_editor_node(state_c)

    doc_after_c: DocArtifact = result_c["doc"]
    history_c: list[ModificationRecord] = result_c["modification_history"]

    # Key assertions from plan: modification_history.length=2, scope same, content grew
    assert len(history_c) == 1  # reducer will add; this is the delta
    assert history_c[0].scope_identifier == "数据分析"
    assert "数据来源" in doc_after_c.sections[1].content_md
    assert len(doc_after_c.sections[1].content_md) > len(doc_after_b.sections[1].content_md)
