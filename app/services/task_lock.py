"""TaskLock: Redis-backed mutex that prevents concurrent execution of the same graph thread."""

from __future__ import annotations

import secrets

import structlog

logger = structlog.get_logger(__name__)

# TTL exceeds Celery hard time limit (360 s) by 60 s so the lock stays alive
# even if the graph runs right up to the kill deadline.
_DEFAULT_TTL = 420

# Lua script: delete key only if its value matches our token (atomic CAS delete).
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


class TaskLock:
    """Acquire/release a Redis NX lock for a given thread_id.

    Uses a random token stored as the key value so that an expired-and-reacquired
    lock cannot be accidentally released by the original holder's ``finally`` block.

    Usage::

        lock = TaskLock(thread_id)
        if not await lock.acquire():
            return  # already running
        try:
            ...  # do work
        finally:
            await lock.release()
    """

    def __init__(self, thread_id: str, ttl: int = _DEFAULT_TTL) -> None:
        self.key = f"task_lock:{thread_id}"
        self.ttl = ttl
        self._token = secrets.token_hex(16)

    async def acquire(self) -> bool:
        """Return True if the lock was acquired, False if already held or on Redis error."""
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings

            async with aioredis.from_url(get_settings().REDIS_URL) as r:  # type: ignore[no-untyped-call]
                acquired = await r.set(self.key, self._token, nx=True, ex=self.ttl)
            return bool(acquired)
        except Exception:
            # Fail-closed: if Redis is down, refuse the lock rather than letting
            # multiple workers run the same thread concurrently.
            logger.exception("task_lock_acquire_failed", key=self.key)
            return False

    async def release(self) -> None:
        """Delete the lock only if it still holds our token (prevents mis-deletion)."""
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings

            async with aioredis.from_url(get_settings().REDIS_URL) as r:  # type: ignore[no-untyped-call]
                await r.eval(_RELEASE_SCRIPT, 1, self.key, self._token)
        except Exception:
            logger.exception("task_lock_release_failed", key=self.key)
