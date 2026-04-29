import redis.asyncio as aioredis

_redis_client: aioredis.Redis | None = None

_KEY_PREFIX = "forge:dedup:"


def set_redis_client(client: aioredis.Redis) -> None:
    global _redis_client
    _redis_client = client


def get_redis_client() -> aioredis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized. Call set_redis_client() first.")
    return _redis_client


async def is_duplicate(event_id: str, ttl: int = 3600) -> bool:
    """Return True if event_id was already seen (duplicate), False if new.

    Uses Redis SET NX EX — atomically sets the key only if it does not exist.
    Returns True (duplicate) when the key already existed.
    """
    client = get_redis_client()
    key = f"{_KEY_PREFIX}{event_id}"
    result = await client.set(key, "1", nx=True, ex=ttl)
    # result is None if key already existed (duplicate), True if newly set
    return result is None
