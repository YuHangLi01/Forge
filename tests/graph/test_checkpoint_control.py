"""Tests for checkpoint_control: detect_control_intent and mid-execution pause."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.checkpoint_control import (  # noqa: E402
    CANCEL_KEYWORDS,
    PAUSE_KEYWORDS,
    RESUME_KEYWORDS,
    detect_control_intent,
)

# ── detect_control_intent ─────────────────────────────────────────────────────


def test_pause_keywords_detected() -> None:
    for kw in PAUSE_KEYWORDS:
        assert detect_control_intent(kw) == "pause", f"missed pause keyword: {kw}"


def test_resume_keywords_detected() -> None:
    for kw in RESUME_KEYWORDS:
        assert detect_control_intent(kw) == "resume", f"missed resume keyword: {kw}"


def test_cancel_keywords_detected() -> None:
    for kw in CANCEL_KEYWORDS:
        assert detect_control_intent(kw) == "cancel", f"missed cancel keyword: {kw}"


def test_pause_embedded_in_sentence() -> None:
    assert detect_control_intent("请暂停一下好吗") == "pause"
    assert detect_control_intent("等等，先不用发") == "pause"
    assert detect_control_intent("停一下，我要修改") == "pause"


def test_resume_embedded_in_sentence() -> None:
    assert detect_control_intent("好了，继续吧") == "resume"
    assert detect_control_intent("可以接着干了") == "resume"


def test_single_等_does_not_trigger_pause() -> None:
    """'等' alone should NOT trigger pause — only '等等' should."""
    assert detect_control_intent("等我一下") is None


def test_unrelated_text_returns_none() -> None:
    assert detect_control_intent("帮我生成一份市场分析报告") is None
    assert detect_control_intent("") is None
    assert detect_control_intent("   ") is None


def test_wait_english_triggers_pause() -> None:
    assert detect_control_intent("wait please") == "pause"
    assert detect_control_intent("Please wait") == "pause"


def test_resume_english_triggers_resume() -> None:
    assert detect_control_intent("resume") == "resume"
    assert detect_control_intent("Please resume") == "resume"


# ── checkpoint_control_node ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkpoint_control_node_emits_pause_card_and_returns_waiting() -> None:
    """Node should send a pause card and return waiting_human status."""
    from app.graph.nodes.checkpoint_control import checkpoint_control_node
    from app.schemas.enums import TaskStatus

    fake_plan = MagicMock()
    fake_plan.steps = [
        MagicMock(node_name="doc_structure_gen"),
        MagicMock(node_name="doc_content_gen"),
        MagicMock(node_name="feishu_doc_write"),
    ]

    state = {
        "message_id": "msg_abc",
        "completed_steps": ["doc_structure_gen"],
        "plan": fake_plan,
    }

    with patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter:
        mock_adapter_instance = AsyncMock()
        MockAdapter.return_value = mock_adapter_instance

        result = await checkpoint_control_node(state)

    mock_adapter_instance.reply_card.assert_awaited_once()
    call_args = mock_adapter_instance.reply_card.call_args
    assert call_args[0][0] == "msg_abc"
    card = call_args[0][1]
    assert card["header"]["template"] == "yellow"

    assert result["status"] == TaskStatus.waiting_human
    assert result["_pause_reason"] == "user_paused"
    assert result["pending_user_action"]["kind"] == "user_paused"


@pytest.mark.asyncio
async def test_checkpoint_control_node_no_plan() -> None:
    """Node handles missing plan gracefully."""
    from app.graph.nodes.checkpoint_control import checkpoint_control_node
    from app.schemas.enums import TaskStatus

    state = {"message_id": "msg_xyz", "completed_steps": [], "plan": None}

    with patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter:
        mock_adapter_instance = AsyncMock()
        MockAdapter.return_value = mock_adapter_instance
        result = await checkpoint_control_node(state)

    assert result["status"] == TaskStatus.waiting_human


@pytest.mark.asyncio
async def test_checkpoint_control_node_feishu_error_does_not_raise() -> None:
    """Feishu card send failure should be swallowed — graph must not crash."""
    from app.graph.nodes.checkpoint_control import checkpoint_control_node

    state = {"message_id": "msg_err", "completed_steps": [], "plan": None}

    with patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter:
        mock_adapter_instance = AsyncMock()
        mock_adapter_instance.reply_card.side_effect = RuntimeError("feishu down")
        MockAdapter.return_value = mock_adapter_instance

        result = await checkpoint_control_node(state)

    assert "status" in result


# ── step_router pause routing ─────────────────────────────────────────────────


def test_step_router_routes_pause_to_checkpoint_control() -> None:
    """step_router should route pending_user_action='pause' to checkpoint_control."""
    from app.graph.nodes.step_router import route

    state: dict = {
        "status": None,
        "pending_user_action": "pause",
        "intent": None,
        "plan": None,
        "completed_steps": [],
    }
    assert route(state) == "checkpoint_control"


def test_step_router_routes_other_pending_to_end() -> None:
    """step_router should return END for non-pause pending actions."""
    from langgraph.graph import END

    from app.graph.nodes.step_router import route

    state: dict = {
        "status": None,
        "pending_user_action": {"kind": "plan_confirm"},
        "intent": None,
        "plan": None,
        "completed_steps": [],
    }
    assert route(state) == END
