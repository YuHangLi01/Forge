"""Tests for ProgressBroadcaster throttle behaviour.

The broadcaster must respect the 1-second throttle: if begin_node is called
5 times within 1 second, update_card should be called at most once immediately
(the first call acquires the Redis lock) — the remaining payloads are parked
in progress_pending:{message_id} for the flush task.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import app.services.progress_broadcaster as pb_mod


def _make_redis_mock(acquired_first: bool = True) -> MagicMock:
    """Return a mock Redis client where SETNX returns True the first time, False after."""
    r = MagicMock()
    r.set.side_effect = [acquired_first] + [False] * 10
    r.getdel.return_value = None
    return r


def test_broadcaster_sends_immediately_when_lock_acquired() -> None:
    """First begin_node call should fire _send_update directly."""
    mock_redis = _make_redis_mock(acquired_first=True)
    mock_redis.get.return_value = None  # no cached card_message_id yet

    with patch.object(pb_mod.redis, "from_url", return_value=mock_redis):
        b = pb_mod.ProgressBroadcaster(message_id="om_test", thread_id="thread_test")
        with patch.object(b, "_send_update") as mock_send:
            b.begin_node("doc_structure_gen")
            # Lock acquired → _send_update called
            mock_send.assert_called_once()

    # Redis set called once (for throttle lock)
    assert mock_redis.set.call_count == 1


def test_broadcaster_parks_when_throttled() -> None:
    """Calls that hit the throttle (setnx returns False) should write to pending key."""
    mock_redis = _make_redis_mock(acquired_first=False)

    with patch.object(pb_mod.redis, "from_url", return_value=mock_redis):
        b = pb_mod.ProgressBroadcaster(message_id="om_throttled", thread_id="t1")
        with patch.object(b, "_send_update") as mock_send:
            b.begin_node("doc_content_gen")
            # Lock NOT acquired → _send_update NOT called
            mock_send.assert_not_called()

    # set called twice: once for lock attempt (returns False), once to park payload
    assert mock_redis.set.call_count == 2
    second_call_args = mock_redis.set.call_args_list[1]
    assert "progress_pending:om_throttled" in str(second_call_args)


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


def test_broadcaster_five_calls_within_second() -> None:
    """5 rapid begin_node calls: first fires, rest park (simulate 1 lock acquisition)."""
    mock_redis = MagicMock()
    # First set call = lock acquired, subsequent ones = throttled
    mock_redis.set.side_effect = [True] + [False] * 10

    with patch.object(pb_mod.redis, "from_url", return_value=mock_redis):
        b = pb_mod.ProgressBroadcaster(message_id="om_burst", thread_id="t_burst")
        send_count = 0

        def counting_send(card: object) -> None:  # noqa: ANN401
            nonlocal send_count
            send_count += 1

        b._send_update = counting_send  # type: ignore[method-assign]

        for i in range(5):
            b.begin_node(f"node_{i}")

    # Only 1 direct send (first acquired lock); rest went to pending key
    assert send_count == 1
    # Redis.set called: 1 throttle-acquire + 4 pending-park = 5 times + 1 lock acquire
    assert mock_redis.set.call_count >= 5
