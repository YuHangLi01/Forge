"""Coverage tests for app.tasks.card_tasks async helpers."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_graph_mock(state_values: dict | None = None):
    """Return an AsyncMock graph with aget_state / aupdate_state / ainvoke."""
    from unittest.mock import AsyncMock, MagicMock

    graph = AsyncMock()
    state = MagicMock()
    state.values = state_values or {}
    graph.aget_state = AsyncMock(return_value=state)
    graph.aupdate_state = AsyncMock(return_value=None)
    graph.ainvoke = AsyncMock(return_value={"status": "completed"})
    return graph


# ---------------------------------------------------------------------------
# _handle_card_action_async dispatch
# ---------------------------------------------------------------------------


class TestHandleCardActionAsync:
    @pytest.mark.asyncio
    async def test_unhandled_action_kind(self) -> None:
        from app.tasks.card_tasks import _handle_card_action_async

        payload = {"event": {"action": {"value": {"action": "unknown_action"}}}}
        result = await _handle_card_action_async(payload)
        assert result["status"] == "unhandled"

    @pytest.mark.asyncio
    async def test_empty_payload(self) -> None:
        from app.tasks.card_tasks import _handle_card_action_async

        result = await _handle_card_action_async({})
        assert result["status"] == "unhandled"


# ---------------------------------------------------------------------------
# _handle_clarify_submit
# ---------------------------------------------------------------------------


class TestHandleClarifySubmit:
    @pytest.mark.asyncio
    async def test_missing_ids_returns_invalid(self) -> None:
        from app.tasks.card_tasks import _handle_clarify_submit

        result = await _handle_clarify_submit({}, {})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_empty_answer_returns_invalid(self, monkeypatch) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_clarify_submit

        with patch("app.tasks.card_tasks._reply_text", new_callable=AsyncMock) as mock_reply:
            result = await _handle_clarify_submit(
                {"request_id": "r1", "thread_id": "t1", "clarify_answer": ""},
                {},
            )
        assert result["status"] == "invalid"
        assert result.get("reason") == "empty_answer"
        mock_reply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stale_request_id(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_clarify_submit

        graph = _make_graph_mock(
            state_values={"pending_user_action": {"request_id": "OLD"}, "chat_id": "c1"}
        )
        with (
            patch("app.tasks.card_tasks._get_graph", return_value=graph, create=True),
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
        ):
            result = await _handle_clarify_submit(
                {"request_id": "NEW", "thread_id": "t1", "clarify_answer": "hello"},
                {},
            )
        assert result["status"] == "stale"

    @pytest.mark.asyncio
    async def test_aget_state_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_clarify_submit

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("redis down"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_clarify_submit(
                {"request_id": "r1", "thread_id": "t1", "clarify_answer": "yes"},
                {},
            )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_successful_submit(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.card_tasks import _handle_clarify_submit

        graph = _make_graph_mock(
            state_values={"pending_user_action": {"request_id": "r1"}, "chat_id": "chat1"}
        )
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._send_progress_card", new_callable=AsyncMock),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_clarify_submit(
                {"request_id": "r1", "thread_id": "t1", "clarify_answer": "yes"},
                {},
            )
        assert result["status"] == "dispatched"


# ---------------------------------------------------------------------------
# _handle_plan_confirm
# ---------------------------------------------------------------------------


class TestHandlePlanConfirm:
    @pytest.mark.asyncio
    async def test_missing_thread_id(self) -> None:
        from app.tasks.card_tasks import _handle_plan_confirm

        result = await _handle_plan_confirm({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_successful_confirm(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.card_tasks import _handle_plan_confirm

        graph = _make_graph_mock(state_values={"chat_id": "chat1"})
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._send_progress_card", new_callable=AsyncMock),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_plan_confirm({"thread_id": "t1"})
        assert result["status"] == "dispatched"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_plan_confirm

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_plan_confirm({"thread_id": "t1"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _handle_plan_cancel
# ---------------------------------------------------------------------------


class TestHandlePlanCancel:
    @pytest.mark.asyncio
    async def test_missing_thread_id(self) -> None:
        from app.tasks.card_tasks import _handle_plan_cancel

        result = await _handle_plan_cancel({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_successful_cancel(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_plan_cancel

        graph = _make_graph_mock(state_values={"chat_id": "c1"})
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._clear_active_task_async", new_callable=AsyncMock),
            patch("app.tasks.card_tasks._reply_text", new_callable=AsyncMock),
        ):
            result = await _handle_plan_cancel({"thread_id": "t1"})
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_plan_cancel

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_plan_cancel({"thread_id": "t1"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _handle_plan_replan
# ---------------------------------------------------------------------------


class TestHandlePlanReplan:
    @pytest.mark.asyncio
    async def test_missing_thread_id(self) -> None:
        from app.tasks.card_tasks import _handle_plan_replan

        result = await _handle_plan_replan({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_successful_replan(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_plan_replan

        graph = _make_graph_mock(state_values={"chat_id": "c1"})
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._clear_active_task_async", new_callable=AsyncMock),
            patch("app.tasks.card_tasks._reply_text", new_callable=AsyncMock),
        ):
            result = await _handle_plan_replan({"thread_id": "t1"})
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_plan_replan

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_plan_replan({"thread_id": "t1"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _handle_task_continue
# ---------------------------------------------------------------------------


class TestHandleTaskContinue:
    @pytest.mark.asyncio
    async def test_missing_thread_id(self) -> None:
        from app.tasks.card_tasks import _handle_task_continue

        result = await _handle_task_continue({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_successful_continue(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.card_tasks import _handle_task_continue

        graph = _make_graph_mock(state_values={"chat_id": "c1"})
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._send_progress_card", new_callable=AsyncMock),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_task_continue({"thread_id": "t1"})
        assert result["status"] == "dispatched"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_task_continue

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_task_continue({"thread_id": "t1"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _handle_checkpoint_resume
# ---------------------------------------------------------------------------


class TestHandleCheckpointResume:
    @pytest.mark.asyncio
    async def test_missing_thread_id(self) -> None:
        from app.tasks.card_tasks import _handle_checkpoint_resume

        result = await _handle_checkpoint_resume({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_successful_resume(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.card_tasks import _handle_checkpoint_resume

        graph = _make_graph_mock(state_values={"chat_id": "c1"})
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._send_progress_card", new_callable=AsyncMock),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_checkpoint_resume({"thread_id": "t1"})
        assert result["status"] == "dispatched"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_checkpoint_resume

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_checkpoint_resume({"thread_id": "t1"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _handle_mod_target
# ---------------------------------------------------------------------------


class TestHandleModTarget:
    @pytest.mark.asyncio
    async def test_missing_thread_id(self) -> None:
        from app.tasks.card_tasks import _handle_mod_target

        result = await _handle_mod_target({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_both_target_unsupported(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_mod_target

        with patch("app.tasks.card_tasks._reply_text", new_callable=AsyncMock):
            result = await _handle_mod_target({"thread_id": "t1", "target": "both"})
        assert result["status"] == "unsupported"

    @pytest.mark.asyncio
    async def test_successful_mod_target(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.card_tasks import _handle_mod_target

        graph = _make_graph_mock(
            state_values={
                "chat_id": "c1",
                "pending_user_action": {
                    "scope_type": "full",
                    "scope_identifier": "全部",
                    "modification_type": "rewrite",
                    "instruction": "test",
                },
            }
        )
        mock_task = MagicMock()
        mock_task.delay = MagicMock()
        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.card_tasks._send_progress_card", new_callable=AsyncMock),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_mod_target({"thread_id": "t1", "target": "document"})
        assert result["status"] == "dispatched"

    @pytest.mark.asyncio
    async def test_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_mod_target

        graph = _make_graph_mock()
        graph.aget_state = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            result = await _handle_mod_target({"thread_id": "t1", "target": "document"})
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _handle_lego_start
# ---------------------------------------------------------------------------


class TestHandleLegoStart:
    @pytest.mark.asyncio
    async def test_missing_fields_returns_invalid(self) -> None:
        from app.tasks.card_tasks import _handle_lego_start

        result = await _handle_lego_start({})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_no_scenarios_returns_invalid(self) -> None:
        from app.tasks.card_tasks import _handle_lego_start

        result = await _handle_lego_start({"chat_id": "c1", "scenarios": []})
        assert result["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_successful_lego_start(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _handle_lego_start

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

        with (
            patch("redis.asyncio.from_url", return_value=mock_redis),
            patch("app.tasks.card_tasks._reply_text", new_callable=AsyncMock),
        ):
            result = await _handle_lego_start(
                {"chat_id": "c1", "thread_id": "t1", "scenarios": ["C", "D"]}
            )
        assert result["status"] == "waiting_for_text"

    @pytest.mark.asyncio
    async def test_redis_exception_returns_error(self) -> None:
        from unittest.mock import patch

        from app.tasks.card_tasks import _handle_lego_start

        with patch("redis.asyncio.from_url", side_effect=RuntimeError("redis down")):
            result = await _handle_lego_start(
                {"chat_id": "c1", "thread_id": "t1", "scenarios": ["C"]}
            )
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _clear_active_task_async
# ---------------------------------------------------------------------------


class TestClearActiveTaskAsync:
    @pytest.mark.asyncio
    async def test_no_chat_id_returns_early(self) -> None:
        from app.tasks.card_tasks import _clear_active_task_async

        await _clear_active_task_async("", "t1")  # should not raise

    @pytest.mark.asyncio
    async def test_clears_matching_key(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _clear_active_task_async

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.get = AsyncMock(return_value=b"t1")
        mock_redis.delete = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await _clear_active_task_async("c1", "t1")
        mock_redis.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_clear_different_thread(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _clear_active_task_async

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.get = AsyncMock(return_value=b"other_thread")
        mock_redis.delete = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            await _clear_active_task_async("c1", "t1")
        mock_redis.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# _send_progress_card / _reply_text
# ---------------------------------------------------------------------------


class TestSendProgressCard:
    @pytest.mark.asyncio
    async def test_sends_card(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _send_progress_card

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock()
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _send_progress_card("msg1", "processing…")
        mock_adapter.reply_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _send_progress_card

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock(side_effect=RuntimeError("network error"))
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _send_progress_card("msg1", "processing…")  # should not raise


class TestReplyText:
    @pytest.mark.asyncio
    async def test_sends_text(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _reply_text

        mock_adapter = AsyncMock()
        mock_adapter.reply_text = AsyncMock()
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _reply_text("msg1", "Hello")
        mock_adapter.reply_text.assert_awaited_once_with("msg1", "Hello")

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.card_tasks import _reply_text

        mock_adapter = AsyncMock()
        mock_adapter.reply_text = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _reply_text("msg1", "Hello")  # should not raise
