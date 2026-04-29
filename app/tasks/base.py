from typing import Any

import httpx
import structlog
from celery import Task

from app.logging import bind_task_context
from app.tasks.celery_app import celery_app

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
