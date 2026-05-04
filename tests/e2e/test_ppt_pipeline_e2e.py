"""E2E tests for the PPT-creation pipeline (execution phase).

Injects a pre-built intent + plan into state so step_router begins at
ppt_structure_gen without going through the planner's plan_confirm pause.
Mocks LLMService and Feishu services; uses InMemorySaver for checkpointing.

Covers: ppt_structure_gen → ppt_content_gen → feishu_ppt_write → delivery_node → END
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graph.builder import build_graph
from app.schemas.artifacts import PPTArtifact
from app.schemas.enums import OutputFormat, TaskStatus, TaskType
from app.schemas.intent import IntentSchema
from app.schemas.plan import PlanSchema, PlanStep
from app.schemas.ppt import PPTBriefSchema, SlideBrief

# ── helpers ──────────────────────────────────────────────────────────────────


def _ppt_intent() -> IntentSchema:
    return IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="制作产品发布PPT",
        output_formats=[OutputFormat.presentation],
        target_audience="全员",
        style_hint="科技感",
        ambiguity_score=0.0,
    )


def _ppt_plan() -> PlanSchema:
    return PlanSchema(
        steps=[
            PlanStep(id="s1", node_name="ppt_structure_gen"),
            PlanStep(id="s2", node_name="ppt_content_gen", depends_on=["s1"]),
            PlanStep(id="s3", node_name="feishu_ppt_write", depends_on=["s2"]),
        ]
    )


def _ppt_brief() -> PPTBriefSchema:
    return PPTBriefSchema(
        title="产品发布",
        target_audience="全员",
        slides=[
            SlideBrief(slide_index=0, page_type="cover", title="产品发布 2026"),
            SlideBrief(
                slide_index=1,
                page_type="content",
                title="产品亮点",
                bullet_points=["更快", "更智能", "更简单"],
            ),
        ],
    )


def _ppt_artifact() -> PPTArtifact:
    return PPTArtifact(
        ppt_id="ppt-e2e-001",
        title="产品发布",
        share_url="https://feishu.cn/slides/ppt-e2e-001",
    )


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def memory_graph():
    """Compiled graph with InMemorySaver — no external deps."""
    return build_graph(MemorySaver())


def _base_state() -> dict:
    """Pre-built state: intent + plan injected so step_router starts at ppt_structure_gen."""
    return {
        "task_id": "task-e2e-ppt-001",
        "user_id": "u-001",
        "chat_id": "chat-001",
        "message_id": "msg-ppt-001",
        "raw_input": "帮我做一个产品发布的PPT",
        "normalized_text": "帮我做一个产品发布的PPT",
        "intent": _ppt_intent(),
        "plan": _ppt_plan(),
        # context_retrieval completed; step_router skips to plan execution
        "completed_steps": ["preprocess", "context_retrieval"],
    }


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ppt_pipeline_happy_path(memory_graph) -> None:
    """Execution-phase PPT pipeline terminates with status=completed and ppt artifact."""
    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=_ppt_brief()),
        ),
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value='{"heading": "标题", "bullets": ["要点1"]}'),
        ),
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new=AsyncMock(return_value=_ppt_artifact()),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=AsyncMock()),
        patch("app.integrations.feishu.adapter.FeishuAdapter.send_card", new=AsyncMock()),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_artifact"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_plan_preview"),
    ):
        final_state = await memory_graph.ainvoke(
            _base_state(),
            config={"configurable": {"thread_id": "e2e-ppt-happy"}},
        )

    assert final_state["status"] == TaskStatus.completed
    assert final_state.get("ppt") is not None
    assert "delivery_node" in (final_state.get("completed_steps") or [])


@pytest.mark.asyncio
async def test_ppt_pipeline_feishu_write_failure_routes_to_error_handler(
    memory_graph,
) -> None:
    """When feishu_ppt_write raises, graph routes to error_handler and sets completed."""
    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=_ppt_brief()),
        ),
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value='{"heading": "标题", "bullets": []}'),
        ),
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new=AsyncMock(side_effect=RuntimeError("Feishu 503 Service Unavailable")),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=AsyncMock()),
        patch("app.integrations.feishu.adapter.FeishuAdapter.send_card", new=AsyncMock()),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_error"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_plan_preview"),
    ):
        state = _base_state()
        state["task_id"] = "task-e2e-ppt-err"
        state["message_id"] = "msg-ppt-err"
        final_state = await memory_graph.ainvoke(
            state,
            config={"configurable": {"thread_id": "e2e-ppt-err"}},
        )

    # error_handler sets status=completed to avoid re-trigger on resume
    assert final_state["status"] == TaskStatus.completed
    assert final_state.get("ppt") is None
