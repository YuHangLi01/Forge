from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)


@forge_task(name="forge.handle_card_action", queue="fast")  # type: ignore[untyped-decorator]
def handle_card_action_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Handle Feishu interactive card button clicks."""
    logger.info("card_action_received", payload=payload)
    return asyncio.run(_handle_card_action_async(payload))


async def _handle_card_action_async(payload: dict[str, Any]) -> dict[str, Any]:
    action: dict[str, Any] = payload.get("event", {}).get("action", {}) or {}
    value: dict[str, Any] = action.get("value", {}) or {}
    form_value: dict[str, Any] = action.get("form_value", {}) or {}

    action_kind = value.get("action", "")

    if action_kind == "clarify_submit":
        return await _handle_clarify_submit(value, form_value)
    if action_kind == "plan_confirm":
        return await _handle_plan_confirm(value)
    if action_kind == "plan_cancel":
        return await _handle_plan_cancel(value)
    if action_kind == "plan_replan":
        return await _handle_plan_replan(value)

    logger.warning("card_action_unhandled", action_kind=action_kind)
    return {"status": "unhandled"}


async def _handle_clarify_submit(
    value: dict[str, Any],
    form_value: dict[str, Any],
) -> dict[str, Any]:
    request_id: str = value.get("request_id", "")
    thread_id: str = value.get("thread_id", "")
    clarify_answer: str = form_value.get("clarify_answer", "").strip()

    if not request_id or not thread_id:
        logger.warning("clarify_submit_missing_ids", request_id=request_id, thread_id=thread_id)
        return {"status": "invalid"}

    from app.graph import get_or_init_graph

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # Stale request_id guard
    try:
        current_state = await graph.aget_state(config)
        pending = (current_state.values or {}).get("pending_user_action") or {}
        if pending.get("request_id") != request_id:
            logger.info(
                "clarify_submit_stale",
                expected=pending.get("request_id"),
                received=request_id,
            )
            return {"status": "stale"}
        chat_id: str = (current_state.values or {}).get("chat_id", "")
    except Exception:
        logger.exception("clarify_stale_check_failed", thread_id=thread_id)
        return {"status": "error"}

    # Inject answer and clear pending gate, then dispatch to slow queue
    await graph.aupdate_state(
        config,
        {"clarify_answer": clarify_answer, "pending_user_action": None},
        as_node="clarify_resume",
    )

    await _send_progress_card(thread_id, "⏳ 正在处理您的回答，请稍候…")

    from app.tasks.message_tasks import resume_graph_task

    resume_graph_task.delay(thread_id, chat_id)

    logger.info("clarify_resumed", thread_id=thread_id, answer_len=len(clarify_answer))
    return {"status": "dispatched", "thread_id": thread_id}


async def _handle_plan_confirm(value: dict[str, Any]) -> dict[str, Any]:
    """User clicked '确认执行' — clear pending gate, send progress card, dispatch to slow queue."""
    thread_id: str = value.get("thread_id", "")
    if not thread_id:
        logger.warning("plan_confirm_missing_thread_id")
        return {"status": "invalid"}

    from app.graph import get_or_init_graph

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = await graph.aget_state(config)
        chat_id: str = (state.values or {}).get("chat_id", "") if state else ""

        await graph.aupdate_state(config, {"pending_user_action": None}, as_node="planner")

        # Immediate feedback so user knows something is happening
        # thread_id == original message_id (see message_tasks.py)
        await _send_progress_card(thread_id, "⏳ 正在执行计划，请稍候…")

        from app.tasks.message_tasks import resume_graph_task

        resume_graph_task.delay(thread_id, chat_id)

        logger.info("plan_confirm_dispatched", thread_id=thread_id)
        return {"status": "dispatched", "thread_id": thread_id}
    except Exception:
        logger.exception("plan_confirm_failed", thread_id=thread_id)
        return {"status": "error"}


async def _handle_plan_cancel(value: dict[str, Any]) -> dict[str, Any]:
    """User clicked '取消' on plan preview — cancel thread and confirm to user."""
    thread_id: str = value.get("thread_id", "")
    if not thread_id:
        logger.warning("plan_cancel_missing_thread_id")
        return {"status": "invalid"}

    from app.graph import get_or_init_graph
    from app.schemas.enums import TaskStatus

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        await graph.aupdate_state(
            config,
            {"status": TaskStatus.cancelled, "pending_user_action": None, "error": "用户取消计划"},
            as_node="planner",
        )
        await _reply_text(thread_id, "已取消当前任务，如需重新生成请重新发送消息 ✅")
        logger.info("plan_cancelled", thread_id=thread_id)
        return {"status": "cancelled", "thread_id": thread_id}
    except Exception:
        logger.exception("plan_cancel_failed", thread_id=thread_id)
        return {"status": "error"}


async def _handle_plan_replan(value: dict[str, Any]) -> dict[str, Any]:
    """User clicked '重新规划' — cancel and prompt user to re-describe."""
    thread_id: str = value.get("thread_id", "")
    if not thread_id:
        return {"status": "invalid"}

    from app.graph import get_or_init_graph
    from app.schemas.enums import TaskStatus

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        await graph.aupdate_state(
            config,
            {"status": TaskStatus.cancelled, "pending_user_action": None, "error": "用户重新规划"},
            as_node="planner",
        )
        await _reply_text(thread_id, "已取消当前计划，请重新描述您的需求 🔄")
        logger.info("plan_replan_cancelled", thread_id=thread_id)
        return {"status": "cancelled", "thread_id": thread_id}
    except Exception:
        logger.exception("plan_replan_failed", thread_id=thread_id)
        return {"status": "error"}


async def _send_progress_card(message_id: str, text: str) -> None:
    """Reply to the original Feishu message with an immediate progress card."""
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.progress_broadcaster import ProgressBroadcaster

    card = ProgressBroadcaster._build_progress_card(text)
    try:
        await FeishuAdapter().reply_card(message_id, card)
    except Exception:
        logger.exception("send_progress_card_failed", message_id=message_id)


async def _reply_text(message_id: str, text: str) -> None:
    """Reply to the original Feishu message with a plain text message."""
    from app.integrations.feishu.adapter import FeishuAdapter

    try:
        await FeishuAdapter().reply_text(message_id, text)
    except Exception:
        logger.exception("reply_text_failed", message_id=message_id)
