"""TaskLock: Redis-backed mutex that prevents concurrent execution of the same graph thread."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class TaskLock:
    """Acquire/release a Redis NX lock for a given thread_id.

    Usage::

        lock = TaskLock(thread_id)
        if not await lock.acquire():
            return  # already running
        try:
            ...  # do work
        finally:
            await lock.release()
    """

    def __init__(self, thread_id: str, ttl: int = 300) -> None:
        self.key = f"task_lock:{thread_id}"
        self.ttl = ttl

    async def acquire(self) -> bool:
        """Return True if the lock was acquired, False if already held."""
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings

            async with aioredis.from_url(get_settings().REDIS_URL) as r:  # type: ignore[no-untyped-call]
                acquired = await r.set(self.key, "1", nx=True, ex=self.ttl)
            return bool(acquired)
        except Exception:
            logger.exception("task_lock_acquire_failed", key=self.key)
            return True  # fail open — don't block execution on Redis errors

    async def release(self) -> None:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings

            async with aioredis.from_url(get_settings().REDIS_URL) as r:  # type: ignore[no-untyped-call]
                await r.delete(self.key)
        except Exception:
            logger.exception("task_lock_release_failed", key=self.key)
