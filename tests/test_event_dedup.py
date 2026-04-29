from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.event_dedup import get_redis_client, is_duplicate, set_redis_client


@pytest.fixture
def mock_redis() -> MagicMock:
    client = MagicMock()
    set_redis_client(client)
    yield client
    # Reset
    import app.services.event_dedup as dedup_module

    dedup_module._redis_client = None


def test_get_redis_client_raises_without_init() -> None:
    import app.services.event_dedup as dedup_module

    original = dedup_module._redis_client
    dedup_module._redis_client = None
    try:
        with pytest.raises(RuntimeError, match="not initialized"):
            get_redis_client()
    finally:
        dedup_module._redis_client = original


async def test_is_duplicate_returns_false_for_new_event(mock_redis: MagicMock) -> None:
    mock_redis.set = AsyncMock(return_value=True)
    result = await is_duplicate("event_001")
    assert result is False
    mock_redis.set.assert_called_once_with("forge:dedup:event_001", "1", nx=True, ex=3600)


async def test_is_duplicate_returns_true_for_seen_event(mock_redis: MagicMock) -> None:
    mock_redis.set = AsyncMock(return_value=None)
    result = await is_duplicate("event_001")
    assert result is True


async def test_is_duplicate_custom_ttl(mock_redis: MagicMock) -> None:
    mock_redis.set = AsyncMock(return_value=True)
    await is_duplicate("event_002", ttl=7200)
    mock_redis.set.assert_called_once_with("forge:dedup:event_002", "1", nx=True, ex=7200)
