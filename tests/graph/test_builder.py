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
    assert len(WORK_NODES) == 11
    assert len(ALL_NODES) == 13  # 11 work + step_router + error_handler


def test_build_graph_returns_different_instances() -> None:
    g1 = build_graph(None)
    g2 = build_graph(None)
    assert g1 is not g2


@pytest.mark.asyncio
async def test_graph_can_invoke_end_to_end() -> None:
    """Stub graph runs preprocess → step_router → END without error."""
    compiled = build_graph(None)
    result = await compiled.ainvoke(
        {
            "task_id": "t1",
            "user_id": "u1",
            "chat_id": "c1",
            "message_id": "m1",
            "raw_input": "hello",
            "completed_steps": [],
            "modification_history": [],
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
