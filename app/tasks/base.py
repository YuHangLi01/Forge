from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

import httpx
import structlog
from celery import Task

from app.logging import bind_task_context
from app.tasks.celery_app import celery_app

# ── Persistent worker event loop ──────────────────────────────────────────────
# asyncio.run() creates AND closes a new loop on every invocation.  When the
# graph singleton (AsyncConnectionPool, AsyncPostgresSaver) is created in the
# first loop, it binds asyncio.Locks to that loop.  The second asyncio.run()
# opens a NEW loop → cached objects still reference the closed first loop →
# RuntimeError: "Lock is bound to a different event loop".
#
# Solution: keep one event loop alive for the entire worker process lifetime.
# Celery prefork workers are separate OS processes, so this is safe.

_loop_lock = threading.Lock()
_worker_loop: asyncio.AbstractEventLoop | None = None
_T = TypeVar("_T")


def run_sync(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run *coro* in the persistent worker event loop (never closes it)."""
    global _worker_loop
    with _loop_lock:
        if _worker_loop is None or _worker_loop.is_closed():
            _worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_worker_loop)
        loop = _worker_loop
    return loop.run_until_complete(coro)


logger = structlog.get_logger(__name__)


class ForgeTask(Task):  # type: ignore[misc]
    """Base Celery task with structlog context injection and auto-retry for network errors."""

    abstract = True
    autoretry_for = (httpx.HTTPError, ConnectionError)
    retry_backoff = True
    retry_backoff_max = 30
    max_retries = 3

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        task_id = self.request.id or "unknown"
        with bind_task_context(task_id=task_id):
            return super().__call__(*args, **kwargs)

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
            exc_type=type(exc).__name__,
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        logger.warning(
            "task_retrying",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
            retry_count=self.request.retries,
        )


def forge_task(name: str, queue: str = "slow", **kwargs: Any) -> Any:
    """Decorator factory: @forge_task(name="...", queue="...") def my_task(...)."""
    return celery_app.task(
        name=name,
        base=ForgeTask,
        bind=True,
        queue=queue,
        **kwargs,
    )
