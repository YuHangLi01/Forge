from __future__ import annotations

from typing import Any

import structlog

from app.tasks.base import forge_task, run_sync

logger = structlog.get_logger(__name__)


@forge_task(name="forge.handle_card_action", queue="fast")  # type: ignore[untyped-decorator]
def handle_card_action_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Handle Feishu interactive card button clicks."""
    logger.info("card_action_received", payload=payload)
    return run_sync(_handle_card_action_async(payload))


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
    if action_kind == "task_continue":
        return await _handle_task_continue(value)
    if action_kind == "checkpoint_resume":
        return await _handle_checkpoint_resume(value)
    if action_kind == "mod_target":
        return await _handle_mod_target(value)
    if action_kind == "lego_start":
        return await _handle_lego_start(value)

    logger.warning("card_action_unhandled", action_kind=action_kind)
    return {"status": "unhandled"}


async def _handle_clarify_submit(
    value: dict[str, Any],
    form_value: dict[str, Any],
) -> dict[str, Any]:
    request_id: str = value.get("request_id", "")
    thread_id: str = value.get("thread_id", "")
    # form_value is only populated for Feishu form-input elements; button clicks
    # carry their payload flat inside value — check both to support both card types.
    clarify_answer: str = (
        form_value.get("clarify_answer") or value.get("clarify_answer", "")
    ).strip()

    if not request_id or not thread_id:
        logger.warning("clarify_submit_missing_ids", request_id=request_id, thread_id=thread_id)
        return {"status": "invalid"}

    if not clarify_answer:
        logger.info("clarify_submit_empty_answer", thread_id=thread_id)
        await _reply_text(thread_id, "请输入您的回答后再提交 🙏")
        return {"status": "invalid", "reason": "empty_answer"}

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

    # Inject answer and clear pending gate, then let step_router route to
    # clarify_resume.  Using as_node="step_router" causes LangGraph to evaluate
    # route(new_state) immediately; the new clarify_answer triggers Priority 2.5
    # → "clarify_resume", so the node body actually runs on next ainvoke.
    await graph.aupdate_state(
        config,
        {"clarify_answer": clarify_answer, "pending_user_action": None},
        as_node="step_router",
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

        await graph.aupdate_state(config, {"pending_user_action": None}, as_node="step_router")

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
        state = await graph.aget_state(config)
        chat_id: str = (state.values or {}).get("chat_id", "") if state else ""

        await graph.aupdate_state(
            config,
            {"status": TaskStatus.cancelled, "pending_user_action": None, "error": "用户取消计划"},
            as_node="planner",
        )
        await _clear_active_task_async(chat_id, thread_id)
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
        state = await graph.aget_state(config)
        chat_id: str = (state.values or {}).get("chat_id", "") if state else ""

        await graph.aupdate_state(
            config,
            {"status": TaskStatus.cancelled, "pending_user_action": None, "error": "用户重新规划"},
            as_node="planner",
        )
        await _clear_active_task_async(chat_id, thread_id)
        await _reply_text(thread_id, "已取消当前计划，请重新描述您的需求 🔄")
        logger.info("plan_replan_cancelled", thread_id=thread_id)
        return {"status": "cancelled", "thread_id": thread_id}
    except Exception:
        logger.exception("plan_replan_failed", thread_id=thread_id)
        return {"status": "error"}


async def _handle_task_continue(value: dict[str, Any]) -> dict[str, Any]:
    """User clicked '继续' on the timeout card — re-dispatch graph continuation."""
    thread_id: str = value.get("thread_id", "")
    if not thread_id:
        return {"status": "invalid"}

    from app.graph import get_or_init_graph

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = await graph.aget_state(config)
        chat_id: str = (state.values or {}).get("chat_id", "") if state else ""

        await _send_progress_card(thread_id, "⏳ 继续处理中，请稍候…")

        from app.tasks.message_tasks import resume_graph_task

        resume_graph_task.delay(thread_id, chat_id)
        logger.info("task_continue_dispatched", thread_id=thread_id)
        return {"status": "dispatched", "thread_id": thread_id}
    except Exception:
        logger.exception("task_continue_failed", thread_id=thread_id)
        return {"status": "error"}


async def _clear_active_task_async(chat_id: str, thread_id: str) -> None:
    """Remove active_task Redis key if it still points to this thread."""
    if not chat_id or not thread_id:
        return
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        r: aioredis.Redis = aioredis.from_url(get_settings().REDIS_URL)  # type: ignore[no-untyped-call]
        key = f"active_task:{chat_id}"
        async with r:
            raw = await r.get(key)
            if raw and (raw.decode() if isinstance(raw, bytes) else raw) == thread_id:
                await r.delete(key)
    except Exception:
        logger.exception("active_task_clear_failed", chat_id=chat_id)


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


async def _handle_checkpoint_resume(value: dict[str, Any]) -> dict[str, Any]:
    """User clicked '▶️ 继续' on the pause card — resume graph from checkpoint."""
    thread_id: str = value.get("thread_id", "")
    if not thread_id:
        logger.warning("checkpoint_resume_missing_thread_id")
        return {"status": "invalid"}

    from app.graph import get_or_init_graph
    from app.schemas.enums import TaskStatus

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = await graph.aget_state(config)
        chat_id: str = (state.values or {}).get("chat_id", "") if state else ""

        await graph.aupdate_state(
            config,
            {"pending_user_action": None, "status": TaskStatus.running},
            as_node="checkpoint_control",
        )
        await _send_progress_card(thread_id, "▶️ 继续执行中，请稍候…")

        from app.tasks.message_tasks import resume_graph_task

        resume_graph_task.delay(thread_id, chat_id)
        logger.info("checkpoint_resumed", thread_id=thread_id)
        return {"status": "dispatched", "thread_id": thread_id}
    except Exception:
        logger.exception("checkpoint_resume_failed", thread_id=thread_id)
        return {"status": "error"}


async def _handle_mod_target(value: dict[str, Any]) -> dict[str, Any]:
    """User chose a modification target (doc / presentation / both) from clarify card."""
    thread_id: str = value.get("thread_id", "")
    target: str = value.get("target", "document")
    if not thread_id:
        logger.warning("mod_target_missing_thread_id")
        return {"status": "invalid"}

    if target == "both":
        await _reply_text(thread_id, "暂不支持同时修改文档和PPT，请分别发送修改指令。")
        return {"status": "unsupported"}

    from app.graph import get_or_init_graph
    from app.schemas.intent import ModificationIntent

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = await graph.aget_state(config)
        vals = (state.values or {}) if state else {}
        chat_id: str = vals.get("chat_id", "")
        pending: dict[str, Any] = vals.get("pending_user_action") or {}

        mod_intent = ModificationIntent(
            target=target,
            scope_type=pending.get("scope_type", "full"),
            scope_identifier=pending.get("scope_identifier", "全部"),
            modification_type=pending.get("modification_type", "rewrite"),
            instruction=pending.get("instruction", ""),
            ambiguity_high=False,
        )

        await graph.aupdate_state(
            config,
            {"pending_user_action": None, "mod_intent": mod_intent},
            as_node="mod_intent_parser",
        )
        await _send_progress_card(thread_id, "✏️ 正在处理修改，请稍候…")

        from app.tasks.message_tasks import resume_graph_task

        resume_graph_task.delay(thread_id, chat_id)
        logger.info("mod_target_resolved", thread_id=thread_id, target=target)
        return {"status": "dispatched", "thread_id": thread_id}
    except Exception:
        logger.exception("mod_target_failed", thread_id=thread_id)
        return {"status": "error"}


async def _handle_lego_start(value: dict[str, Any]) -> dict[str, Any]:
    """User selected lego scenarios — store in Redis and ask for description."""
    import json as _json

    chat_id: str = value.get("chat_id", "")
    thread_id: str = value.get("thread_id", "")
    scenarios: list[str] = value.get("scenarios", [])
    if not chat_id or not scenarios:
        logger.warning("lego_start_missing_fields", chat_id=chat_id, scenarios=scenarios)
        return {"status": "invalid"}

    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        r: aioredis.Redis = aioredis.from_url(get_settings().REDIS_URL)  # type: ignore[no-untyped-call]
        async with r:
            await r.setex(f"pending_lego:{chat_id}", 300, _json.dumps(scenarios))

        prompt = "好的，请直接在对话框输入你的需求（例如：围绕推送改版做演示）👇"
        await _reply_text(thread_id, prompt)
        logger.info("lego_start_waiting", chat_id=chat_id, scenarios=scenarios)
        return {"status": "waiting_for_text", "scenarios": scenarios}
    except Exception:
        logger.exception("lego_start_failed", chat_id=chat_id)
        return {"status": "error"}
