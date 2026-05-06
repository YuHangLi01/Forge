from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ForgeTask
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)


async def create_task(
    session: AsyncSession,
    task_id: str,
    user_id: str,
    chat_id: str,
) -> ForgeTask:
    task = ForgeTask(
        task_id=task_id,
        user_id=user_id,
        chat_id=chat_id,
        status=TaskStatus.pending,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    logger.info("task_created", task_id=task_id)
    return task


async def get_task_by_id(session: AsyncSession, task_id: str) -> ForgeTask | None:
    result = await session.execute(select(ForgeTask).where(ForgeTask.task_id == task_id))
    return result.scalar_one_or_none()


async def update_task_status(
    session: AsyncSession,
    task_id: str,
    status: TaskStatus,
    error: str | None = None,
) -> bool:
    task = await get_task_by_id(session, task_id)
    if task is None:
        logger.warning("task_not_found", task_id=task_id)
        return False
    task.status = status
    task.updated_at = datetime.now(UTC)
    if error is not None:
        task.error = error
    if status == TaskStatus.completed and task.delivered_at is None:
        task.delivered_at = datetime.now(UTC)
    await session.commit()
    logger.info("task_status_updated", task_id=task_id, status=status)
    return True


async def update_task_artifacts(
    session: AsyncSession,
    task_id: str,
    *,
    doc_id: str | None = None,
    ppt_id: str | None = None,
    plan_json: dict[str, object] | None = None,
) -> bool:
    task = await get_task_by_id(session, task_id)
    if task is None:
        logger.warning("task_not_found_for_artifacts", task_id=task_id)
        return False
    if doc_id is not None:
        task.doc_id = doc_id
    if ppt_id is not None:
        task.ppt_id = ppt_id
    if plan_json is not None:
        task.plan_json = plan_json
    task.updated_at = datetime.now(UTC)
    await session.commit()
    logger.info("task_artifacts_updated", task_id=task_id, doc_id=doc_id, ppt_id=ppt_id)
    return True
