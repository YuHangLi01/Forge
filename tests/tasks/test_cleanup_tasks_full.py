"""Coverage tests for app.tasks.cleanup_tasks async helpers."""

from __future__ import annotations

import json
import time

import pytest

# ---------------------------------------------------------------------------
# _expire_clarify_actions_async
# ---------------------------------------------------------------------------


def _make_async_redis(keys_and_values: dict[str, str | None] | None = None):
    """Return a minimal async-context-manager Redis mock."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)

    kv = keys_and_values or {}

    # scan returns (cursor=0, list_of_keys) in one shot
    mock.scan = AsyncMock(return_value=(0, list(kv.keys())))
    mock.get = AsyncMock(side_effect=lambda k: kv.get(k if isinstance(k, str) else k.decode()))
    mock.delete = AsyncMock()
    mock.getdel = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    return mock


class TestExpireClarifyActionsAsync:
    @pytest.mark.asyncio
    async def test_no_keys_returns_zero(self) -> None:
        from unittest.mock import patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        mock_r = _make_async_redis({})
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _expire_clarify_actions_async()
        assert result == {"expired": 0}

    @pytest.mark.asyncio
    async def test_fresh_key_not_expired(self) -> None:
        from unittest.mock import patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        meta = json.dumps({"thread_id": "t1", "chat_id": "c1", "waiting_since": time.time()})
        mock_r = _make_async_redis({"clarify:t1": meta})
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _expire_clarify_actions_async()
        assert result == {"expired": 0}

    @pytest.mark.asyncio
    async def test_expired_key_triggers_cancel_and_notify(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        old_ts = time.time() - 4000  # > 3600 s
        meta = json.dumps({"thread_id": "t1", "chat_id": "c1", "waiting_since": old_ts})
        mock_r = _make_async_redis({"clarify:t1": meta})

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.cleanup_tasks._cancel_thread", new_callable=AsyncMock) as mock_cancel,
            patch("app.tasks.cleanup_tasks._notify_expired", new_callable=AsyncMock) as mock_notify,
        ):
            result = await _expire_clarify_actions_async()

        assert result == {"expired": 1}
        mock_cancel.assert_awaited_once_with("t1")
        mock_notify.assert_awaited_once_with("c1")
        mock_r.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_expired_no_chat_id_skips_notify(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        old_ts = time.time() - 4000
        meta = json.dumps({"thread_id": "t1", "chat_id": "", "waiting_since": old_ts})
        mock_r = _make_async_redis({"clarify:t1": meta})

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.cleanup_tasks._cancel_thread", new_callable=AsyncMock),
            patch("app.tasks.cleanup_tasks._notify_expired", new_callable=AsyncMock) as mock_notify,
        ):
            await _expire_clarify_actions_async()

        mock_notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_json_deletes_key(self) -> None:
        from unittest.mock import patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        mock_r = _make_async_redis({"clarify:bad": "not json"})
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _expire_clarify_actions_async()
        mock_r.delete.assert_awaited()
        assert result == {"expired": 0}

    @pytest.mark.asyncio
    async def test_none_value_skips_key(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        mock_r = _make_async_redis()
        mock_r.scan = AsyncMock(return_value=(0, ["clarify:none"]))
        mock_r.get = AsyncMock(return_value=None)

        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _expire_clarify_actions_async()
        assert result == {"expired": 0}

    @pytest.mark.asyncio
    async def test_cancel_exception_does_not_abort(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _expire_clarify_actions_async

        old_ts = time.time() - 4000
        meta = json.dumps({"thread_id": "t1", "chat_id": "c1", "waiting_since": old_ts})
        mock_r = _make_async_redis({"clarify:t1": meta})

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch(
                "app.tasks.cleanup_tasks._cancel_thread",
                new_callable=AsyncMock,
                side_effect=RuntimeError("graph unavailable"),
            ),
            patch("app.tasks.cleanup_tasks._notify_expired", new_callable=AsyncMock),
        ):
            result = await _expire_clarify_actions_async()

        assert result == {"expired": 1}


# ---------------------------------------------------------------------------
# _cancel_thread
# ---------------------------------------------------------------------------


class TestCancelThread:
    @pytest.mark.asyncio
    async def test_empty_thread_id_returns_early(self) -> None:
        from app.tasks.cleanup_tasks import _cancel_thread

        await _cancel_thread("")  # should not raise

    @pytest.mark.asyncio
    async def test_cancels_graph_state(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _cancel_thread

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock()
        with patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph):
            await _cancel_thread("t1")
        graph.aupdate_state.assert_awaited_once()
        call_args = graph.aupdate_state.call_args
        state_update = call_args[0][1]
        assert (
            state_update["status"].value in ("cancelled",)
            or str(state_update["status"]) == "cancelled"
        )


# ---------------------------------------------------------------------------
# _notify_expired
# ---------------------------------------------------------------------------


class TestNotifyExpired:
    @pytest.mark.asyncio
    async def test_sends_message_to_chat(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _notify_expired

        mock_adapter = AsyncMock()
        mock_adapter.send_text = AsyncMock()
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _notify_expired("chat1")
        mock_adapter.send_text.assert_awaited_once()
        args = mock_adapter.send_text.call_args[0]
        assert args[0] == "chat1"
        assert len(args[1]) > 0


# ---------------------------------------------------------------------------
# _flush_pending_progress_async
# ---------------------------------------------------------------------------


class TestFlushPendingProgressAsync:
    @pytest.mark.asyncio
    async def test_no_keys_returns_zero(self) -> None:
        from unittest.mock import patch

        from app.tasks.cleanup_tasks import _flush_pending_progress_async

        mock_r = _make_async_redis({})
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _flush_pending_progress_async()
        assert result == {"flushed": 0}

    @pytest.mark.asyncio
    async def test_flushes_with_existing_card(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _flush_pending_progress_async

        card_json = json.dumps({"header": {"template": "blue"}})
        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.scan = AsyncMock(return_value=(0, [b"progress_pending:msg1"]))
        mock_r.getdel = AsyncMock(return_value=card_json.encode())
        mock_r.get = AsyncMock(return_value=b"card_msg_id_123")
        mock_r.set = AsyncMock()

        mock_adapter = AsyncMock()
        mock_adapter.update_card = AsyncMock()
        mock_adapter.reply_card = AsyncMock(return_value="new_card_id")

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter),
        ):
            result = await _flush_pending_progress_async()

        assert result == {"flushed": 1}
        mock_adapter.update_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flushes_without_existing_card_creates_new(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _flush_pending_progress_async

        card_json = json.dumps({"header": {"template": "blue"}})
        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.scan = AsyncMock(return_value=(0, [b"progress_pending:msg2"]))
        mock_r.getdel = AsyncMock(return_value=card_json.encode())
        mock_r.get = AsyncMock(return_value=None)  # no existing card
        mock_r.set = AsyncMock()

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock(return_value="new_id")
        mock_adapter.update_card = AsyncMock()

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter),
        ):
            result = await _flush_pending_progress_async()

        assert result == {"flushed": 1}
        mock_adapter.reply_card.assert_awaited_once()
        mock_r.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_send_exception_does_not_abort(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _flush_pending_progress_async

        card_json = json.dumps({"header": {}})
        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.scan = AsyncMock(return_value=(0, [b"progress_pending:msg3"]))
        mock_r.getdel = AsyncMock(return_value=card_json.encode())
        mock_r.get = AsyncMock(side_effect=RuntimeError("redis error"))

        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _flush_pending_progress_async()

        assert result == {"flushed": 0}

    @pytest.mark.asyncio
    async def test_getdel_none_skips(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.cleanup_tasks import _flush_pending_progress_async

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.scan = AsyncMock(return_value=(0, [b"progress_pending:msg4"]))
        mock_r.getdel = AsyncMock(return_value=None)

        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _flush_pending_progress_async()

        assert result == {"flushed": 0}
