"""Tests for ProgressBroadcaster throttle behaviour.

The broadcaster must respect the 1-second throttle: if begin_node is called
5 times within 1 second, update_card should be called at most once immediately
(the first call acquires the Redis lock) — the remaining payloads are parked
in progress_pending:{message_id} for the flush task.

All Redis I/O is now async (redis.asyncio); tests mock _emit_async directly or
use AsyncMock to patch the aioredis connection.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import app.services.progress_broadcaster as pb_mod


@pytest.mark.asyncio
async def test_broadcaster_sends_immediately_when_lock_acquired() -> None:
    """_emit_async should call _send_update_async when throttle lock is acquired."""
    b = pb_mod.ProgressBroadcaster(message_id="om_test", thread_id="thread_test")
    b._current_card = pb_mod.ProgressBroadcaster._build_progress_card("test")

    mock_r = AsyncMock()
    mock_r.set = AsyncMock(return_value=True)  # lock acquired
    mock_r.__aenter__ = AsyncMock(return_value=mock_r)
    mock_r.__aexit__ = AsyncMock(return_value=False)

    card = {"test": "card"}

    with (
        patch.object(b, "_send_update_async", new_callable=AsyncMock) as mock_send,
        patch("redis.asyncio.from_url", return_value=mock_r),
    ):
        await b._emit_async(card)

    mock_send.assert_called_once_with(mock_r, card)


@pytest.mark.asyncio
async def test_broadcaster_parks_when_throttled() -> None:
    """_emit_async should park to pending key when throttle lock is NOT acquired."""
    b = pb_mod.ProgressBroadcaster(message_id="om_throttled", thread_id="t1")

    mock_r = AsyncMock()
    mock_r.set = AsyncMock(side_effect=[False, None])  # lock not acquired, then park
    mock_r.__aenter__ = AsyncMock(return_value=mock_r)
    mock_r.__aexit__ = AsyncMock(return_value=False)

    card = {"throttled": "card"}

    with (
        patch.object(b, "_send_update_async", new_callable=AsyncMock) as mock_send,
        patch("redis.asyncio.from_url", return_value=mock_r),
    ):
        await b._emit_async(card)

    mock_send.assert_not_called()
    # The pending key should have been written
    import json

    pending_key = pb_mod._PENDING_KEY.format(message_id="om_throttled")
    mock_r.set.assert_any_call(pending_key, json.dumps(card), ex=10)


def test_broadcaster_emit_error_bypasses_throttle() -> None:
    """emit_error uses _send_now directly, bypassing the Redis throttle."""
    b = pb_mod.ProgressBroadcaster(message_id="om_err", thread_id="t_err")

    with patch.object(b, "_send_now") as mock_send:
        b.emit_error("Something went wrong")
        mock_send.assert_called_once()


def test_react_filter_sanitize_integration() -> None:
    """update_thinking strips thinking blocks; empty result skips _emit."""
    b = pb_mod.ProgressBroadcaster(message_id="om_thinking", thread_id="t_think")

    with patch.object(b, "_emit") as mock_emit:
        # Thinking block strips to empty → no _emit
        b.update_thinking("<thinking>hidden internal state</thinking>")
        mock_emit.assert_not_called()

        # Normal text → _emit called
        b.update_thinking("正在分析文档结构…")
        mock_emit.assert_called_once()


def test_broadcaster_emit_spawns_daemon_thread() -> None:
    """_emit should always spawn a daemon thread running asyncio.run(_emit_async).

    This avoids 'Task was destroyed but it is pending!' in Celery workers where
    the event loop is short-lived and create_task tasks are never executed.
    """
    from unittest.mock import MagicMock

    b = pb_mod.ProgressBroadcaster(message_id="om_thread", thread_id="t_thread")
    b._current_card = {"some": "card"}

    mock_thread_instance = MagicMock()
    mock_thread_cls = MagicMock(return_value=mock_thread_instance)

    with patch("app.services.progress_broadcaster.threading.Thread", mock_thread_cls):
        b._emit()

    mock_thread_cls.assert_called_once()
    _, kwargs = mock_thread_cls.call_args
    assert kwargs.get("daemon") is True
    assert kwargs.get("target") is asyncio.run
    mock_thread_instance.start.assert_called_once()

    # Close the unawaited coroutine that was passed as args to the mock thread
    # to prevent RuntimeWarning from the GC ("coroutine never awaited").
    coro = kwargs["args"][0]
    coro.close()
