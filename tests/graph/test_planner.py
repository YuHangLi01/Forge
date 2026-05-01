"""Tests for planner node — LLM success, retry, template fallback, validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.planner import _TEMPLATE_PLAN, _validate_plan, planner_node
from app.schemas.plan import PlanSchema, PlanStep


def _valid_plan() -> PlanSchema:
    return PlanSchema(
        steps=[
            PlanStep(id="step_1", node_name="doc_structure_gen", depends_on=[]),
            PlanStep(id="step_2", node_name="doc_content_gen", depends_on=["step_1"]),
            PlanStep(id="step_3", node_name="feishu_doc_write", depends_on=["step_2"]),
        ],
        total_estimated_seconds=75,
    )


def _mock_intent(goal: str = "写一份复盘文档") -> MagicMock:
    m = MagicMock()
    m.primary_goal = goal
    m.task_type = "create_new"
    m.output_formats = ["document"]
    return m


# ── validate_plan unit tests ─────────────────────────────────────────────────


def test_validate_plan_valid() -> None:
    assert _validate_plan(_valid_plan()) is True


def test_validate_plan_unknown_node() -> None:
    plan = PlanSchema(
        steps=[PlanStep(id="step_1", node_name="unknown_node", depends_on=[])],
        total_estimated_seconds=10,
    )
    assert _validate_plan(plan) is False


def test_validate_plan_missing_dep() -> None:
    plan = PlanSchema(
        steps=[PlanStep(id="step_1", node_name="doc_structure_gen", depends_on=["step_99"])],
        total_estimated_seconds=10,
    )
    assert _validate_plan(plan) is False


def test_validate_plan_total_too_long() -> None:
    plan = PlanSchema(
        steps=[PlanStep(id="step_1", node_name="doc_structure_gen", depends_on=[])],
        total_estimated_seconds=350,  # > 300s threshold (aligned with CELERY_TASK_SOFT_TIME_LIMIT)
    )
    assert _validate_plan(plan) is False


def test_validate_plan_empty_steps() -> None:
    assert _validate_plan(PlanSchema(steps=[], total_estimated_seconds=0)) is False


# ── planner_node integration tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_planner_returns_valid_plan_from_llm() -> None:
    state = {"intent": _mock_intent(), "retrieved_context": []}

    with patch(
        "app.services.llm_service.LLMService.structured",
        new=AsyncMock(return_value=_valid_plan()),
    ):
        result = await planner_node(state)

    plan: PlanSchema = result["plan"]
    assert len(plan.steps) == 3
    assert plan.steps[0].node_name == "doc_structure_gen"


@pytest.mark.asyncio
async def test_planner_falls_back_to_template_after_llm_failure() -> None:
    state = {"intent": _mock_intent(), "retrieved_context": []}

    with patch(
        "app.services.llm_service.LLMService.structured",
        new=AsyncMock(side_effect=RuntimeError("LLM down")),
    ):
        result = await planner_node(state)

    assert result["plan"] == _TEMPLATE_PLAN


@pytest.mark.asyncio
async def test_planner_falls_back_when_plan_invalid() -> None:
    bad_plan = PlanSchema(
        steps=[PlanStep(id="step_1", node_name="bad_node", depends_on=[])],
        total_estimated_seconds=10,
    )
    state = {"intent": _mock_intent(), "retrieved_context": []}

    with patch(
        "app.services.llm_service.LLMService.structured", new=AsyncMock(return_value=bad_plan)
    ):
        result = await planner_node(state)

    assert result["plan"] == _TEMPLATE_PLAN


@pytest.mark.asyncio
async def test_planner_skipped_when_pending_user_action() -> None:
    state = {
        "intent": _mock_intent(),
        "pending_user_action": {"kind": "clarify"},
    }
    result = await planner_node(state)
    assert result == {}
