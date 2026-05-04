"""Lego orchestration scenario tests: doc+ppt serial chain."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.schemas.enums import OutputFormat, TaskType
from app.schemas.intent import IntentSchema
from app.schemas.plan import PlanSchema


def _make_multi_format_intent() -> IntentSchema:
    return IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="市场分析报告 + PPT",
        output_formats=[OutputFormat.document, OutputFormat.presentation],
        ambiguity_score=0.1,
    )


# ── compose_plan tests ────────────────────────────────────────────────────────


def test_compose_plan_single_scenario_c() -> None:
    """C only: 3 steps, strictly ordered."""
    from app.graph.nodes.lego_orchestrator import compose_plan

    plan = compose_plan(["C"])
    assert len(plan.steps) == 3
    nodes = [s.node_name for s in plan.steps]
    assert nodes == ["doc_structure_gen", "doc_content_gen", "feishu_doc_write"]
    assert plan.steps[0].depends_on == []
    assert plan.steps[1].depends_on == ["C1"]
    assert plan.steps[2].depends_on == ["C2"]


def test_compose_plan_single_scenario_d() -> None:
    """D only: 3 steps, strictly ordered."""
    from app.graph.nodes.lego_orchestrator import compose_plan

    plan = compose_plan(["D"])
    nodes = [s.node_name for s in plan.steps]
    assert nodes == ["ppt_structure_gen", "ppt_content_gen", "feishu_ppt_write"]
    assert plan.steps[0].depends_on == []


def test_compose_plan_cd_chain() -> None:
    """C+D: 6 steps serial; D1 depends on C3 (cross-scenario link)."""
    from app.graph.nodes.lego_orchestrator import compose_plan

    plan = compose_plan(["C", "D"])
    assert len(plan.steps) == 6
    nodes = [s.node_name for s in plan.steps]
    assert nodes == [
        "doc_structure_gen",
        "doc_content_gen",
        "feishu_doc_write",
        "ppt_structure_gen",
        "ppt_content_gen",
        "feishu_ppt_write",
    ]
    d1 = plan.steps[3]
    assert d1.node_name == "ppt_structure_gen"
    assert "C3" in d1.depends_on


def test_compose_plan_estimated_seconds() -> None:
    from app.graph.nodes.lego_orchestrator import compose_plan

    plan = compose_plan(["C", "D"])
    assert plan.total_estimated_seconds > 0


# ── lego_orchestrator_node tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lego_orchestrator_node_writes_plan() -> None:
    """Node converts _lego_scenarios → PlanSchema and writes it to state."""
    from app.graph.nodes.lego_orchestrator import lego_orchestrator_node

    state = {
        "task_id": "lego_test",
        "user_id": "usr_lego",
        "chat_id": "chat_lego",
        "message_id": "msg_lego",
        "_lego_scenarios": ["C", "D"],
        "plan": None,
        "completed_steps": [],
        "pending_user_action": None,
    }

    with patch("app.graph.nodes.lego_orchestrator.ProgressBroadcaster"):
        result = await lego_orchestrator_node(state)

    assert "plan" in result
    plan: PlanSchema = result["plan"]
    assert len(plan.steps) == 6
    assert plan.steps[0].node_name == "doc_structure_gen"
    assert plan.steps[3].node_name == "ppt_structure_gen"


# ── scenario_composer_node tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_composer_doc_and_ppt() -> None:
    """Intent with document+presentation → scenarios ['C', 'D']."""
    from app.graph.nodes.scenario_composer import scenario_composer_node

    intent = _make_multi_format_intent()
    state = {
        "intent": intent,
        "completed_steps": [],
        "pending_user_action": None,
    }

    result = await scenario_composer_node(state)

    assert "_lego_scenarios" in result
    assert "C" in result["_lego_scenarios"]
    assert "D" in result["_lego_scenarios"]


@pytest.mark.asyncio
async def test_scenario_composer_doc_only() -> None:
    """Intent with document only → scenarios ['C']."""
    from app.graph.nodes.scenario_composer import scenario_composer_node

    intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="产品分析文档",
        output_formats=[OutputFormat.document],
        ambiguity_score=0.0,
    )
    state = {"intent": intent, "completed_steps": [], "pending_user_action": None}

    result = await scenario_composer_node(state)
    assert result["_lego_scenarios"] == ["C"]


@pytest.mark.asyncio
async def test_scenario_composer_ppt_only() -> None:
    """Intent with presentation only → scenarios ['D']."""
    from app.graph.nodes.scenario_composer import scenario_composer_node

    intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="市场分析PPT",
        output_formats=[OutputFormat.presentation],
        ambiguity_score=0.0,
    )
    state = {"intent": intent, "completed_steps": [], "pending_user_action": None}

    result = await scenario_composer_node(state)
    assert result["_lego_scenarios"] == ["D"]


# ── step_router integration ───────────────────────────────────────────────────


def test_step_router_routes_multi_format_to_scenario_composer() -> None:
    """Multi-format intent with no lego_scenarios → route to scenario_composer."""
    from app.graph.nodes.step_router import route

    intent = _make_multi_format_intent()
    state: dict = {
        "status": None,
        "pending_user_action": None,
        "intent": intent,
        "_lego_scenarios": None,
        "plan": None,
        "completed_steps": ["context_retrieval"],  # context already retrieved
        "clarify_answer": None,
        "clarify_count": 0,
        "mod_intent": None,
    }
    assert route(state) == "scenario_composer"


def test_step_router_routes_to_lego_orchestrator_when_scenarios_set() -> None:
    """Multi-format intent with _lego_scenarios → route to lego_orchestrator."""
    from app.graph.nodes.step_router import route

    intent = _make_multi_format_intent()
    state: dict = {
        "status": None,
        "pending_user_action": None,
        "intent": intent,
        "_lego_scenarios": ["C", "D"],
        "plan": None,
        "completed_steps": ["context_retrieval"],
        "clarify_answer": None,
        "clarify_count": 0,
        "mod_intent": None,
    }
    assert route(state) == "lego_orchestrator"


def test_plan_next_runnable_step_follows_serial_lego_chain() -> None:
    """Plan follows strict C→D ordering, not executing D until C is done."""
    from app.graph.nodes.lego_orchestrator import compose_plan

    plan = compose_plan(["C", "D"])
    completed: set[str] = set()

    expected_order = [
        "doc_structure_gen",
        "doc_content_gen",
        "feishu_doc_write",
        "ppt_structure_gen",
        "ppt_content_gen",
        "feishu_ppt_write",
    ]

    actual_order: list[str] = []
    for node_name in expected_order:
        step = plan.next_runnable_step(completed)
        assert step is not None, f"Expected {node_name} but got None"
        assert step.node_name == node_name, f"Expected {node_name}, got {step.node_name}"
        actual_order.append(step.node_name)
        completed.add(node_name)

    assert actual_order == expected_order
    assert plan.next_runnable_step(completed) is None
