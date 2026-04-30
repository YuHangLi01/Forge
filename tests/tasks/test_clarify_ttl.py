"""Tests for clarify TTL expiry (cleanup_tasks.expire_clarify_actions)."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.cleanup_tasks import _expire_clarify_actions_async


def _make_redis_mock(entries: dict[str, dict]) -> MagicMock:
    """Build an async-context-manager Redis mock with given scan/get entries."""
    r = MagicMock()
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)

    keys = list(entries.keys())
    r.scan = AsyncMock(return_value=(0, keys))

    async def fake_get(key: str):
        entry = entries.get(key)
        return json.dumps(entry).encode() if entry else None

    r.get = fake_get
    r.delete = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_expired_clarify_action_is_cancelled() -> None:
    old_time = time.time() - 3700  # 1h 1m 40s ago — expired
    entries = {
        b"clarify:req-old": {
            "thread_id": "thread-001",
            "chat_id": "chat-abc",
            "request_id": "req-old",
            "waiting_since": old_time,
        }
    }

    mock_redis = _make_redis_mock(entries)
    with (
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("app.tasks.cleanup_tasks._cancel_thread", new=AsyncMock()) as mock_cancel,
        patch("app.tasks.cleanup_tasks._notify_expired", new=AsyncMock()) as mock_notify,
    ):
        result = await _expire_clarify_actions_async()

    assert result["expired"] == 1
    mock_cancel.assert_awaited_once_with("thread-001")
    mock_notify.assert_awaited_once_with("chat-abc")
    mock_redis.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_fresh_clarify_action_not_cancelled() -> None:
    fresh_time = time.time() - 60  # only 1 minute ago — not expired
    entries = {
        b"clarify:req-fresh": {
            "thread_id": "thread-002",
            "chat_id": "chat-xyz",
            "request_id": "req-fresh",
            "waiting_since": fresh_time,
        }
    }

    mock_redis = _make_redis_mock(entries)

    with (
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("app.tasks.cleanup_tasks._cancel_thread", new=AsyncMock()) as mock_cancel,
        patch("app.tasks.cleanup_tasks._notify_expired", new=AsyncMock()) as mock_notify,
    ):
        result = await _expire_clarify_actions_async()

    assert result["expired"] == 0
    mock_cancel.assert_not_awaited()
    mock_notify.assert_not_awaited()
    mock_redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_json_key_is_deleted() -> None:
    r = MagicMock()
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    r.scan = AsyncMock(return_value=(0, [b"clarify:bad"]))
    r.get = AsyncMock(return_value=b"not-json{{")
    r.delete = AsyncMock()

    with (
        patch("redis.asyncio.from_url", return_value=r),
        patch("app.tasks.cleanup_tasks._cancel_thread", new=AsyncMock()),
        patch("app.tasks.cleanup_tasks._notify_expired", new=AsyncMock()),
    ):
        result = await _expire_clarify_actions_async()

    # Bad JSON entry deleted but not counted as expired task
    r.delete.assert_awaited_once()
    assert result["expired"] == 0


@pytest.mark.asyncio
async def test_no_entries_returns_zero() -> None:
    r = MagicMock()
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    r.scan = AsyncMock(return_value=(0, []))
    r.delete = AsyncMock()

    with patch("redis.asyncio.from_url", return_value=r):
        result = await _expire_clarify_actions_async()

    assert result["expired"] == 0
