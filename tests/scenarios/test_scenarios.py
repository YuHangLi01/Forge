"""End-to-end scenario tests: node-pipeline integration (no full graph needed).

Scenario A: doc pipeline — doc_structure_gen → doc_content_gen → feishu_doc_write
            Assertion: final doc has ≥3 sections, status=completed
Scenario C: modification chain — doc_section_editor called twice on same scope
            Assertion: modification_history length=2, same scope_identifier both records
Scenario B: planner fallback — LLM fails → template plan used + pending_user_action set
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.artifacts import DocArtifact, DocSection
from app.schemas.doc_outline import DocOutline, DocOutlineSection
from app.schemas.enums import TaskStatus, TaskType
from app.schemas.intent import IntentSchema, ModificationIntent
from app.schemas.modification import ModificationRecord
from app.schemas.plan import PlanSchema

# ── shared helpers ────────────────────────────────────────────────────────────


def _create_intent(task_type: TaskType = TaskType.create_new) -> MagicMock:
    m = MagicMock(spec=IntentSchema)
    m.task_type = task_type
    m.primary_goal = "写一份产品复盘文档"
    m.output_formats = ["document"]
    m.target_audience = "高管"
    m.style_hint = "专业简洁"
    m.ambiguity_score = 0.0
    m.missing_info = []
    return m


def _create_doc(n_sections: int = 3) -> DocArtifact:
    sections = [
        DocSection(id=f"s{i}", title=f"章节{i + 1}", content_md=f"内容{i + 1}段落。" * 5)
        for i in range(n_sections)
    ]
    return DocArtifact(
        doc_id="doc-test-001",
        title="产品复盘文档",
        sections=sections,
        share_url="https://feishu.test/doc-test-001",
    )


def _outline(n: int = 3) -> DocOutline:
    return DocOutline(
        document_title="产品复盘文档",
        sections=[DocOutlineSection(id=f"s{i}", title=f"章节{i + 1}") for i in range(n)],
    )


def _mod_intent(scope: str = "章节1") -> ModificationIntent:
    return ModificationIntent(
        target="document",
        scope_type="specific_section",
        scope_identifier=scope,
        modification_type="rewrite",
        instruction="请改写得更简洁",
    )


_BASE_STATE: dict = {
    "task_id": "task_test",
    "user_id": "user_test",
    "chat_id": "chat_test",
    "message_id": "msg_test",
    "completed_steps": [],
    "modification_history": [],
    "retrieved_context": [],
    "completed_section_ids": [],
    "pending_user_action": None,
    "status": TaskStatus.pending,
    "error": None,
}


# ── Scenario A: doc creation pipeline ────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_a_doc_pipeline() -> None:
    """doc_structure_gen → doc_content_gen → feishu_doc_write pipeline.
    Assertions: doc has ≥3 sections, final status=completed.

    Note: builder.py compiles work nodes as _stub_node references (not importable
    patches), so we test the real node functions directly in pipeline sequence.
    """
    from app.graph.nodes.doc_content_gen import doc_content_gen_node
    from app.graph.nodes.doc_structure_gen import doc_structure_gen_node
    from app.graph.nodes.feishu_doc_write import feishu_doc_write_node

    intent = _create_intent()
    outline = _outline(3)
    final_doc = _create_doc(3)

    state: dict = {
        **_BASE_STATE,
        "intent": intent,
        "retrieved_context": [],
    }

    # Step 1: doc_structure_gen
    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=outline),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.update_card", new=AsyncMock()),
    ):
        s1 = await doc_structure_gen_node(state)

    assert "doc_outline" in s1
    assert len(s1["doc_outline"]["sections"]) == 3

    # Step 2: doc_content_gen
    state2 = {**state, **s1}
    with (
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value="内容段落。" * 10),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.update_card", new=AsyncMock()),
    ):
        s2 = await doc_content_gen_node(state2)

    assert "doc" in s2
    assert len(s2["doc"].sections) >= 3

    # Step 3: feishu_doc_write
    state3 = {**state2, **s2}
    with (
        patch(
            "app.services.feishu_doc_service.FeishuDocService.create_from_markdown",
            new=AsyncMock(return_value=final_doc),
        ),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.set_permission_public",
            new=AsyncMock(),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.update_card", new=AsyncMock()),
    ):
        s3 = await feishu_doc_write_node(state3)

    result_doc = s3.get("doc")
    assert result_doc is not None, "doc should be set after feishu_doc_write"
    assert len(result_doc.sections) >= 3
    assert s3.get("status") == TaskStatus.completed


# ── Scenario C: modification chain ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_c_modification_chain() -> None:
    """doc_section_editor called twice on the same scope.
    modification_history should contain 2 records with the same scope_identifier.
    """
    doc = _create_doc(3)
    scope = "章节1"
    new_content = "改写后的章节1内容，更加简洁。"

    state1 = {
        "task_id": "task_scenario_c_step1",
        "user_id": "user_c",
        "chat_id": "chat_c",
        "message_id": "msg_c1",
        "normalized_text": "请把章节1改简洁",
        "doc": doc,
        "mod_intent": _mod_intent(scope),
        "modification_history": [],
        "retrieved_context": [],
        "intent": _create_intent(TaskType.modify_existing),
        "completed_steps": [],
        "pending_user_action": None,
        "status": TaskStatus.pending,
        "error": None,
    }

    with (
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value=new_content),
        ),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.update_card",
            new=AsyncMock(),
        ),
    ):
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        result1 = await doc_section_editor_node(state1)

    assert len(result1.get("modification_history", [])) == 1
    assert result1["modification_history"][0].scope_identifier == scope

    # Second modification on the same scope
    doc_after_first = result1.get("doc", doc)
    history_after_first: list[ModificationRecord] = result1.get("modification_history", [])

    state2 = {
        **state1,
        "message_id": "msg_c2",
        "normalized_text": "章节1再加一些数据来源",
        "doc": doc_after_first,
        "mod_intent": ModificationIntent(
            target="document",
            scope_type="specific_section",
            scope_identifier=scope,
            modification_type="append",
            instruction="请在末尾加上数据来源说明",
        ),
        "modification_history": history_after_first,
    }

    with (
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value=new_content + "\n数据来源：内部报告2026Q3"),
        ),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.update_card",
            new=AsyncMock(),
        ),
    ):
        result2 = await doc_section_editor_node(state2)

    final_history = history_after_first + result2.get("modification_history", [])
    assert len(final_history) == 2, f"Expected 2 history records, got {len(final_history)}"
    assert all(
        r.scope_identifier == scope for r in final_history
    ), "Both modifications should target the same scope"


# ── Scenario B: planner fallback ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_b_planner_template_fallback() -> None:
    """When LLM fails, planner uses template fallback and plan is still valid."""
    from app.graph.nodes.planner import planner_node

    intent = _create_intent()
    state = {
        "message_id": "msg_b",
        "intent": intent,
        "retrieved_context": [],
        "pending_user_action": None,
    }

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(side_effect=RuntimeError("LLM timeout")),
        ),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.update_card",
            new=AsyncMock(),
        ),
    ):
        result = await planner_node(state)

    plan = result.get("plan")
    assert isinstance(plan, PlanSchema), "Should fall back to template PlanSchema"
    assert len(plan.steps) >= 1
    assert result.get("pending_user_action") is not None
