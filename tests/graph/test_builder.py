"""Tests for build_graph — verifies the StateGraph compiles and all nodes are registered."""

import pytest

from app.graph.builder import ALL_NODES, WORK_NODES, build_graph


def test_build_graph_compiles_with_none_checkpointer() -> None:
    compiled = build_graph(None)
    assert compiled is not None


def test_build_graph_compiles_without_argument() -> None:
    compiled = build_graph()
    assert compiled is not None


def test_all_work_nodes_in_all_nodes_list() -> None:
    for node in WORK_NODES:
        assert node in ALL_NODES


def test_all_nodes_count() -> None:
    assert len(WORK_NODES) == 15  # 11 doc-pipeline + 4 ppt-pipeline
    assert len(ALL_NODES) == 17  # 15 work + step_router + error_handler


def test_build_graph_returns_different_instances() -> None:
    g1 = build_graph(None)
    g2 = build_graph(None)
    assert g1 is not g2


@pytest.mark.asyncio
async def test_graph_can_invoke_end_to_end() -> None:
    """Stub graph reaches END when plan has no remaining steps.

    With stub nodes (all returning {}), state never changes on its own.
    We prime the state so step_router immediately routes to END via the
    plan-driven path, avoiding infinite recursion.
    """
    from unittest.mock import MagicMock

    compiled = build_graph(None)

    # Build a mock plan whose next_runnable_step always returns None (all done)
    done_plan = MagicMock()
    done_plan.next_runnable_step.return_value = None

    # Build a mock intent that is clear (low ambiguity, create_new)
    from app.schemas.enums import TaskType

    clear_intent = MagicMock()
    clear_intent.task_type = TaskType.create_new
    clear_intent.ambiguity_score = 0.0

    result = await compiled.ainvoke(
        {
            "task_id": "t1",
            "user_id": "u1",
            "chat_id": "c1",
            "message_id": "m1",
            "raw_input": "hello",
            "completed_steps": ["context_retrieval"],  # retrieval already done
            "modification_history": [],
            "intent": clear_intent,
            "plan": done_plan,
        }
    )
    assert result is not None


def test_get_graph_singleton_returns_same_instance() -> None:
    from app.graph import get_graph, reset_graph

    reset_graph()
    g1 = get_graph()
    g2 = get_graph()
    assert g1 is g2
    reset_graph()


def test_reset_graph_clears_singleton() -> None:
    from app.graph import get_graph, reset_graph

    reset_graph()
    g1 = get_graph()
    reset_graph()
    g2 = get_graph()
    assert g1 is not g2
    reset_graph()
