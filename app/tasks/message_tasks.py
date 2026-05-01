import asyncio
import json
from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)


@forge_task(name="forge.handle_message", queue="slow")  # type: ignore[untyped-decorator]
def handle_message_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    event = payload.get("event", {})
    message = event.get("message", {}) if isinstance(event, dict) else {}
    raw_header = payload.get("header")
    event_id = raw_header.get("event_id", "") if isinstance(raw_header, dict) else ""

    logger.info("message_received", event_id=event_id, message_type=message.get("message_type"))

    return asyncio.run(_handle_message_async(payload))


async def _handle_message_async(payload: dict[str, Any]) -> dict[str, Any]:
    from app.config import get_settings
    from app.services.message_router import parse_message

    msg = parse_message(payload)

    if msg.message_type == "unsupported":
        logger.info("unsupported_message_type", message_id=msg.message_id)
        return {"status": "received", "message_type": "unsupported"}

    settings = get_settings()
    if settings.FORGE_USE_GRAPH:
        return await _handle_via_graph(msg, payload)

    return await _handle_stage1(msg)


async def _handle_via_graph(msg: Any, payload: Any) -> dict[str, Any]:
    """Stage 2: invoke the LangGraph agent pipeline."""
    from app.db.engine import get_session
    from app.graph import get_or_init_graph
    from app.repositories.task_repo import create_task, update_task_status
    from app.schemas.agent_state import make_agent_state
    from app.schemas.enums import TaskStatus

    initial_state = make_agent_state(
        user_id=msg.sender_user_id,
        chat_id=msg.chat_id,
        message_id=msg.message_id,
    )
    initial_state["raw_input"] = msg.text
    task_id: str = initial_state["task_id"]

    if msg.message_type == "audio" and msg.file_key:
        initial_state["attachments"] = [
            {"type": "audio", "file_key": msg.file_key, "message_id": msg.message_id}
        ]

    # D-6: create task row before graph starts
    try:
        async with get_session() as session:
            await create_task(
                session,
                task_id=task_id,
                user_id=msg.sender_user_id,
                chat_id=msg.chat_id,
            )
    except Exception:
        logger.exception("task_create_db_failed", task_id=task_id)

    config = {"configurable": {"thread_id": msg.message_id or msg.event_id}}
    thread_id: str = msg.message_id or msg.event_id or ""

    # FIX-4: register active task so a "取消" message in the same chat can cancel it
    if msg.chat_id and thread_id:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings as _get_settings

            settings_now = _get_settings()
            r: aioredis.Redis = aioredis.from_url(settings_now.REDIS_URL)  # type: ignore[no-untyped-call]
            async with r:
                await r.setex(f"active_task:{msg.chat_id}", 600, thread_id)
        except Exception:
            logger.exception("active_task_register_failed", chat_id=msg.chat_id)

    try:
        graph = await get_or_init_graph()
        result = await graph.ainvoke(initial_state, config=config)
        final_status = result.get("status", TaskStatus.completed)
        logger.info("graph_completed", message_id=msg.message_id, status=final_status)

        # D-6: update task row after graph finishes
        try:
            async with get_session() as session:
                await update_task_status(session, task_id, TaskStatus.completed)
        except Exception:
            logger.exception("task_update_db_failed", task_id=task_id)

        _clear_active_task(msg.chat_id, thread_id)
        return {"status": "completed", "message_id": msg.message_id}
    except Exception as exc:
        logger.exception("graph_failed", message_id=msg.message_id, error=str(exc))

        try:
            async with get_session() as session:
                await update_task_status(session, task_id, TaskStatus.failed, error=str(exc))
        except Exception:
            logger.exception("task_fail_update_db_failed", task_id=task_id)

        _clear_active_task(msg.chat_id, thread_id)
        return {"status": "error", "error": str(exc)}


def _clear_active_task(chat_id: str, thread_id: str) -> None:
    """Remove active_task Redis key if it still points to this thread."""
    if not chat_id or not thread_id:
        return
    try:
        import redis

        from app.config import get_settings

        r = redis.from_url(get_settings().REDIS_URL)  # type: ignore[no-untyped-call]
        key = f"active_task:{chat_id}"
        raw = r.get(key)
        if raw and (raw.decode() if isinstance(raw, bytes) else raw) == thread_id:
            r.delete(key)
    except Exception:
        logger.exception("active_task_clear_failed", chat_id=chat_id)


async def _handle_stage1(msg: Any) -> dict[str, Any]:
    """Stage 1: direct Celery → service calls (default path, FORGE_USE_GRAPH=False)."""
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.asr_service import ASRService
    from app.services.echo_responder import EchoResponder
    from app.services.intent_router import classify

    feishu = FeishuAdapter()
    asr_svc = ASRService(feishu)
    responder = EchoResponder()

    user_text = msg.text

    if msg.message_type == "audio" and msg.file_key:
        user_text = await asr_svc.transcribe_voice_message(msg.message_id, msg.file_key)
        if not user_text:
            user_text = "[语音内容无法识别]"

    if not user_text.strip():
        return {"status": "received", "message_type": msg.message_type}

    intent = classify(user_text)
    if intent == "generate_demo":
        from app.tasks.demo_tasks import handle_demo_request_task

        handle_demo_request_task.delay({"event": {"message": {}}, "header": {}})
        logger.info("demo_task_dispatched", message_id=msg.message_id, text=user_text)
        return {"status": "dispatched", "intent": "generate_demo"}

    try:
        reply = await responder.respond(msg.chat_id, msg.message_id, user_text)
        if msg.message_id:
            await feishu.reply_text(msg.message_id, reply)
        else:
            await feishu.send_text(msg.chat_id, reply)
    except Exception as exc:
        logger.exception("message_handler_failed", message_id=msg.message_id, error=str(exc))
        _error_reply = "抱歉，处理出错，请稍后重试。"
        try:
            if msg.message_id:
                await feishu.reply_text(msg.message_id, _error_reply)
            else:
                await feishu.send_text(msg.chat_id, _error_reply)
        except Exception:
            logger.exception("error_reply_failed", message_id=msg.message_id)
        return {"status": "error", "error": str(exc)}

    return {"status": "completed", "message_id": msg.message_id}


def _parse_message_content(raw_content: str | None, message_type: str) -> str:
    if not raw_content:
        return ""
    try:
        obj: dict[str, Any] = json.loads(raw_content)
        if message_type == "text":
            return str(obj.get("text", ""))
        if message_type == "audio":
            return str(obj.get("file_key", ""))
    except (json.JSONDecodeError, TypeError):
        pass
    return ""
