"""E2E tests for the document-creation pipeline (execution phase).

Injects a pre-built intent + plan into state so step_router begins at
doc_structure_gen without going through the planner's plan_confirm pause.
Mocks LLMService and Feishu services; uses InMemorySaver for checkpointing.

Covers: doc_structure_gen → doc_content_gen → feishu_doc_write → delivery_node → END
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graph.builder import build_graph
from app.schemas.artifacts import DocArtifact, DocSection
from app.schemas.doc_outline import DocOutline, DocOutlineSection
from app.schemas.enums import OutputFormat, TaskStatus, TaskType
from app.schemas.intent import IntentSchema
from app.schemas.plan import PlanSchema, PlanStep

# ── helpers ──────────────────────────────────────────────────────────────────


def _intent() -> IntentSchema:
    return IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="写一份项目复盘文档",
        output_formats=[OutputFormat.document],
        target_audience="高管",
        style_hint="简洁专业",
        ambiguity_score=0.0,
    )


def _doc_plan() -> PlanSchema:
    return PlanSchema(
        steps=[
            PlanStep(id="s1", node_name="doc_structure_gen"),
            PlanStep(id="s2", node_name="doc_content_gen", depends_on=["s1"]),
            PlanStep(id="s3", node_name="feishu_doc_write", depends_on=["s2"]),
        ]
    )


def _doc_outline() -> DocOutline:
    return DocOutline(
        document_title="Q3复盘",
        sections=[
            DocOutlineSection(id="s0", title="背景"),
            DocOutlineSection(id="s1", title="数据分析"),
            DocOutlineSection(id="s2", title="结论"),
        ],
    )


def _doc_artifact() -> DocArtifact:
    return DocArtifact(
        doc_id="doc-e2e-001",
        title="Q3复盘",
        sections=[DocSection(id="s0", title="背景", content_md="背景内容")],
        share_url="https://feishu.cn/docx/doc-e2e-001",
    )


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def memory_graph():
    """Compiled graph with InMemorySaver — no external deps."""
    return build_graph(MemorySaver())


def _base_state() -> dict:
    """Pre-built state: intent + plan injected so step_router starts at doc_structure_gen."""
    return {
        "task_id": "task-e2e-001",
        "user_id": "u-001",
        "chat_id": "chat-001",
        "message_id": "msg-001",
        "raw_input": "帮我写一份Q3项目复盘文档",
        "normalized_text": "帮我写一份Q3项目复盘文档",
        "intent": _intent(),
        "plan": _doc_plan(),
        # context_retrieval completed; step_router skips to plan execution
        "completed_steps": ["preprocess", "context_retrieval"],
    }


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_doc_pipeline_happy_path(memory_graph) -> None:
    """Execution-phase pipeline terminates with status=completed and doc artifact."""
    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=_doc_outline()),
        ),
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value="# Q3复盘\n\n## 背景\n内容"),
        ),
        patch(
            "app.services.feishu_doc_service.FeishuDocService.create_from_markdown",
            new=AsyncMock(return_value=_doc_artifact()),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=AsyncMock()),
        patch("app.integrations.feishu.adapter.FeishuAdapter.send_card", new=AsyncMock()),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.set_permission_public",
            new=AsyncMock(),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_artifact"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_plan_preview"),
    ):
        final_state = await memory_graph.ainvoke(
            _base_state(),
            config={"configurable": {"thread_id": "e2e-doc-happy"}},
        )

    assert final_state["status"] == TaskStatus.completed
    assert final_state.get("doc") is not None
    assert "delivery_node" in (final_state.get("completed_steps") or [])


@pytest.mark.asyncio
async def test_doc_pipeline_feishu_write_failure_routes_to_error_handler(memory_graph) -> None:
    """When feishu_doc_write raises, graph routes to error_handler and sets completed."""
    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=_doc_outline()),
        ),
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value="# Q3复盘\n\n内容"),
        ),
        patch(
            "app.services.feishu_doc_service.FeishuDocService.create_from_markdown",
            new=AsyncMock(side_effect=RuntimeError("Feishu 500 Internal Server Error")),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=AsyncMock()),
        patch("app.integrations.feishu.adapter.FeishuAdapter.send_card", new=AsyncMock()),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_error"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_plan_preview"),
    ):
        state = _base_state()
        state["task_id"] = "task-e2e-err"
        state["message_id"] = "msg-err"
        final_state = await memory_graph.ainvoke(
            state,
            config={"configurable": {"thread_id": "e2e-doc-err"}},
        )

    # error_handler sets status=completed to avoid re-trigger on resume
    assert final_state["status"] == TaskStatus.completed
    # doc_content_gen sets doc in state; feishu_doc_write failure means no real doc_id
    doc = final_state.get("doc")
    assert doc is None or not getattr(doc, "doc_id", None)
