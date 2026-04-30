"""Cleanup periodic tasks: expire stale clarify actions."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)

_CLARIFY_TTL_SECONDS = 3600  # 1 hour


@forge_task(name="forge.expire_clarify_actions", queue="fast")  # type: ignore[untyped-decorator]
def expire_clarify_actions(self: Any) -> dict[str, Any]:  # noqa: ARG001
    """Celery beat task — runs every 5 min.

    Scans Redis for pending clarify requests older than 1 hour.
    For each expired entry:
      1. Marks the LangGraph thread as cancelled via aupdate_state.
      2. Sends a Feishu text message to the chat.
      3. Removes the Redis key.
    """
    return asyncio.run(_expire_clarify_actions_async())


async def _expire_clarify_actions_async() -> dict[str, Any]:
    import redis.asyncio as aioredis

    from app.config import get_settings

    settings = get_settings()
    r: aioredis.Redis = aioredis.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]

    expired_count = 0
    now = time.time()

    async with r:
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match="clarify:*", count=100)
            for key in keys:
                raw = await r.get(key)
                if raw is None:
                    continue
                try:
                    meta: dict[str, Any] = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    await r.delete(key)
                    continue

                waiting_since: float = meta.get("waiting_since", now)
                if now - waiting_since < _CLARIFY_TTL_SECONDS:
                    continue

                # Expired — cancel graph thread and notify user
                thread_id: str = meta.get("thread_id", "")
                chat_id: str = meta.get("chat_id", "")

                try:
                    await _cancel_thread(thread_id)
                except Exception:
                    logger.exception("clarify_expire_cancel_failed", thread_id=thread_id)

                if chat_id:
                    try:
                        await _notify_expired(chat_id)
                    except Exception:
                        logger.exception("clarify_expire_notify_failed", chat_id=chat_id)

                await r.delete(key)
                expired_count += 1
                logger.info(
                    "clarify_expired",
                    thread_id=thread_id,
                    chat_id=chat_id,
                    age_seconds=int(now - waiting_since),
                )

            if cursor == 0:
                break

    return {"expired": expired_count}


async def _cancel_thread(thread_id: str) -> None:
    if not thread_id:
        return

    from app.graph import get_graph
    from app.schemas.enums import TaskStatus

    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    await graph.aupdate_state(
        config,
        {
            "status": TaskStatus.cancelled,
            "pending_user_action": None,
            "error": "澄清等待超时（1小时），任务已取消",
        },
    )


async def _notify_expired(chat_id: str) -> None:
    from app.integrations.feishu.adapter import FeishuAdapter

    feishu = FeishuAdapter()
    await feishu.send_text(
        chat_id,
        "由于超过 1 小时未收到您的回复，任务已自动取消。如需继续，请重新发送您的请求。",
    )
