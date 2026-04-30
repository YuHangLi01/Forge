"""Tests for context_retrieval node — user isolation + degradation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.context_retrieval import context_retrieval_node
from app.schemas.enums import TaskType


def _mock_intent(task_type: str = "create_new", primary_goal: str = "写一份复盘文档") -> MagicMock:
    m = MagicMock()
    m.task_type = TaskType(task_type)
    m.primary_goal = primary_goal
    return m


@pytest.mark.asyncio
async def test_retrieval_returns_results() -> None:
    state = {
        "user_id": "dev_alice",
        "intent": _mock_intent(),
    }
    fake_results = [{"text": "Q3数据", "metadata": {"user_id": "dev_alice"}, "distance": 0.1}]

    with patch(
        "app.services.chroma_service.ChromaService.query", new=AsyncMock(return_value=fake_results)
    ):
        result = await context_retrieval_node(state)

    assert result["retrieved_context"] == fake_results
    assert "context_retrieval" in result["completed_steps"]


@pytest.mark.asyncio
async def test_modify_path_skips_retrieval() -> None:
    state = {
        "user_id": "dev_alice",
        "intent": _mock_intent(task_type="modify_existing"),
    }
    with patch("app.services.chroma_service.ChromaService.query", new=AsyncMock()) as mock_q:
        result = await context_retrieval_node(state)

    mock_q.assert_not_awaited()
    assert result["retrieved_context"] == []
    assert "context_retrieval" in result["completed_steps"]


@pytest.mark.asyncio
async def test_chroma_error_degrades_to_empty() -> None:
    state = {"user_id": "dev_bob", "intent": _mock_intent()}

    with patch(
        "app.services.chroma_service.ChromaService.query",
        new=AsyncMock(side_effect=RuntimeError("Chroma down")),
    ):
        result = await context_retrieval_node(state)

    assert result["retrieved_context"] == []
    assert "context_retrieval" in result["completed_steps"]


@pytest.mark.asyncio
async def test_empty_query_skips_chroma() -> None:
    state = {"user_id": "dev_alice", "normalized_text": "   ", "intent": None}

    with patch("app.services.chroma_service.ChromaService.query", new=AsyncMock()) as mock_q:
        result = await context_retrieval_node(state)

    mock_q.assert_not_awaited()
    assert result["retrieved_context"] == []


@pytest.mark.asyncio
async def test_pending_user_action_skips_node() -> None:
    """Race protection: node returns {} when graph is paused."""
    state = {
        "user_id": "dev_alice",
        "intent": _mock_intent(),
        "pending_user_action": {"kind": "clarify"},
    }
    result = await context_retrieval_node(state)
    assert result == {}
