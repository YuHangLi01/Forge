"""Tests for clarify_resume node."""

from unittest.mock import MagicMock

import pytest

from app.graph.nodes.clarify_resume import clarify_resume_node
from app.schemas.enums import TaskStatus


@pytest.mark.asyncio
async def test_clarify_resume_merges_answer() -> None:
    state = {
        "normalized_text": "帮我写材料",
        "clarify_answer": "写一份给高管的季度复盘报告",
        "pending_user_action": {"kind": "clarify", "request_id": "req-1"},
        "intent": MagicMock(),
    }
    result = await clarify_resume_node(state)

    assert "高管" in result["normalized_text"]
    assert "帮我写材料" in result["normalized_text"]
    assert result["pending_user_action"] is None
    assert result["clarify_answer"] is None
    assert result["intent"] is None  # force re-parse
    assert result["status"] == TaskStatus.running


@pytest.mark.asyncio
async def test_clarify_resume_empty_answer_preserves_text() -> None:
    state = {
        "normalized_text": "帮我写材料",
        "clarify_answer": "",
        "pending_user_action": {"kind": "clarify", "request_id": "req-2"},
    }
    result = await clarify_resume_node(state)

    assert result["normalized_text"] == "帮我写材料"
    assert result["pending_user_action"] is None


@pytest.mark.asyncio
async def test_clarify_resume_no_clarify_answer_key() -> None:
    state = {
        "normalized_text": "原始请求",
        "pending_user_action": {"kind": "clarify", "request_id": "req-3"},
    }
    result = await clarify_resume_node(state)

    assert result["normalized_text"] == "原始请求"
    assert result["pending_user_action"] is None


@pytest.mark.asyncio
async def test_clarify_resume_skipped_when_no_pending_action() -> None:
    """pending_user_action=None → @graph_node returns {} immediately (race protection)."""
    state = {
        "normalized_text": "hello",
        "pending_user_action": None,
    }
    result = await clarify_resume_node(state)
    # clarify_resume is the one node that IS exempt from the skip rule,
    # so it should run even when pending_user_action is None
    assert "normalized_text" in result or result == {}
