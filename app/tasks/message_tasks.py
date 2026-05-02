import json
from typing import Any

import structlog

from app.tasks.base import forge_task, run_sync

logger = structlog.get_logger(__name__)


@forge_task(name="forge.handle_message", queue="slow")  # type: ignore[untyped-decorator]
def handle_message_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    from billiard.exceptions import SoftTimeLimitExceeded

    event = payload.get("event", {})
    message = event.get("message", {}) if isinstance(event, dict) else {}
    raw_header = payload.get("header")
    event_id = raw_header.get("event_id", "") if isinstance(raw_header, dict) else ""

    logger.info("message_received", event_id=event_id, message_type=message.get("message_type"))

    try:
        return run_sync(_handle_message_async(payload))
    except SoftTimeLimitExceeded:
        # Extract message_id so we can send a timeout card to the user.
        msg_obj = message if isinstance(message, dict) else {}
        message_id: str = msg_obj.get("message_id", "")
        logger.warning("handle_message_timeout", event_id=event_id, message_id=message_id)
        if message_id:
            try:
                run_sync(_send_timeout_card_async(message_id))
            except Exception:
                logger.exception("timeout_card_failed", message_id=message_id)
        return {"status": "timeout", "event_id": event_id}


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

    # /lego slash command — emit scenario selector card
    if msg.text and msg.text.strip().startswith("/lego") and msg.message_id and msg.chat_id:
        return await _handle_lego_command(msg)

    # ── Control intent intercept (pause / resume / cancel) ──────────────────
    if msg.text and msg.chat_id:
        from app.graph.nodes.checkpoint_control import detect_control_intent

        control = detect_control_intent(msg.text)
        if control in ("pause", "resume", "cancel"):
            graph_ctrl = await get_or_init_graph()
            return await _handle_control_intent(msg, control, graph_ctrl)
    # ────────────────────────────────────────────────────────────────────────

    # Message-level idempotency guard.
    # Feishu retries failed webhook deliveries with a *new* event_id, so the
    # webhook-layer event_id dedup does not protect against Feishu retries.
    # We use a Redis SETNX on the message_id to ensure only one graph invocation
    # runs per Feishu message, regardless of how many webhook deliveries arrive.
    if msg.message_id:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings as _gs

            _r: aioredis.Redis = aioredis.from_url(_gs().REDIS_URL)  # type: ignore[no-untyped-call]
            async with _r:
                already_running = not await _r.set(
                    f"forge:msg_run:{msg.message_id}", "1", nx=True, ex=3600
                )
            if already_running:
                logger.info("message_already_processing", message_id=msg.message_id)
                return {"status": "duplicate"}
        except Exception:
            logger.exception("msg_dedup_check_failed", message_id=msg.message_id)

    # ── Clarify-reply intercept ──────────────────────────────────────────────
    # If this chat has a suspended clarify thread, treat the incoming message
    # as the user's answer and resume that thread instead of starting a new one.
    if msg.chat_id and msg.text:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings as _gs_c

            _rc: aioredis.Redis = aioredis.from_url(_gs_c().REDIS_URL)  # type: ignore[no-untyped-call]
            async with _rc:
                raw_clarify = await _rc.get(f"pending_clarify:{msg.chat_id}")
            if raw_clarify:
                clarify_thread_id = (
                    raw_clarify.decode() if isinstance(raw_clarify, bytes) else raw_clarify
                )
                graph_c = await get_or_init_graph()
                clarify_config = {"configurable": {"thread_id": clarify_thread_id}}
                c_state = await graph_c.aget_state(clarify_config)
                c_vals = (c_state.values or {}) if c_state else {}
                pending = c_vals.get("pending_user_action") or {}
                if pending.get("kind") == "clarify":
                    await graph_c.aupdate_state(
                        clarify_config,
                        {"clarify_answer": msg.text.strip(), "pending_user_action": None},
                        as_node="step_router",
                    )
                    async with aioredis.from_url(_gs_c().REDIS_URL) as _rc2:  # type: ignore[no-untyped-call]
                        await _rc2.delete(f"pending_clarify:{msg.chat_id}")
                    logger.info(
                        "clarify_reply_intercepted",
                        chat_id=msg.chat_id,
                        clarify_thread=clarify_thread_id,
                    )
                    result_c = await graph_c.ainvoke(None, clarify_config)
                    logger.info("clarify_thread_resumed", status=result_c.get("status"))
                    return {"status": "completed", "message_id": msg.message_id}
                else:
                    # Thread moved on; stale key — clean it up
                    async with aioredis.from_url(_gs_c().REDIS_URL) as _rc3:  # type: ignore[no-untyped-call]
                        await _rc3.delete(f"pending_clarify:{msg.chat_id}")
        except Exception:
            logger.exception("clarify_reply_intercept_failed", chat_id=msg.chat_id)
    # ────────────────────────────────────────────────────────────────────────

    # Lego text intercept — user typed their description after clicking a lego scenario button
    if msg.chat_id and msg.text and not (msg.text or "").strip().startswith("/"):
        try:
            import json as _json

            import redis.asyncio as aioredis

            from app.config import get_settings as _gs_lego

            _rl: aioredis.Redis = aioredis.from_url(_gs_lego().REDIS_URL)  # type: ignore[no-untyped-call]
            async with _rl:
                raw_lego = await _rl.get(f"pending_lego:{msg.chat_id}")
            if raw_lego:
                lego_scenarios = _json.loads(
                    raw_lego.decode() if isinstance(raw_lego, bytes) else raw_lego
                )
                async with aioredis.from_url(_gs_lego().REDIS_URL) as _rl2:  # type: ignore[no-untyped-call]
                    await _rl2.delete(f"pending_lego:{msg.chat_id}")
                return await _handle_lego_text(msg, lego_scenarios)
        except Exception:
            logger.exception("lego_text_intercept_failed", chat_id=msg.chat_id)

    initial_state = make_agent_state(
        user_id=msg.sender_user_id,
        chat_id=msg.chat_id,
        message_id=msg.message_id,
    )
    initial_state["raw_input"] = msg.text
    task_id: str = initial_state["task_id"]

    # Restore the most-recent DocArtifact for this chat so modify requests
    # in a new message thread can still access the previously generated doc.
    if msg.chat_id:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings as _gs2
            from app.schemas.artifacts import DocArtifact

            _r2: aioredis.Redis = aioredis.from_url(_gs2().REDIS_URL)  # type: ignore[no-untyped-call]
            async with _r2:
                raw_doc = await _r2.get(f"active_doc:{msg.chat_id}")
            if raw_doc:
                initial_state["doc"] = DocArtifact.model_validate_json(raw_doc)
        except Exception:
            logger.exception("active_doc_restore_failed", chat_id=msg.chat_id)

    # Restore most-recent PPTArtifact for modify requests
    if msg.chat_id:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings as _gs3
            from app.schemas.artifacts import PPTArtifact

            _r3: aioredis.Redis = aioredis.from_url(_gs3().REDIS_URL)  # type: ignore[no-untyped-call]
            async with _r3:
                raw_ppt = await _r3.get(f"active_ppt:{msg.chat_id}")
            if raw_ppt:
                initial_state["ppt"] = PPTArtifact.model_validate_json(raw_ppt)
        except Exception:
            logger.exception("active_ppt_restore_failed", chat_id=msg.chat_id)

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


@forge_task(name="forge.resume_graph", queue="slow")  # type: ignore[untyped-decorator]
def resume_graph_task(self: Any, thread_id: str, chat_id: str = "") -> dict[str, Any]:
    """Continue a suspended LangGraph thread (after plan confirm, clarify submit, etc.)."""
    from billiard.exceptions import SoftTimeLimitExceeded

    try:
        return run_sync(_resume_graph_async(thread_id, chat_id))
    except SoftTimeLimitExceeded:
        logger.warning("resume_graph_timeout", thread_id=thread_id)
        try:
            run_sync(_send_timeout_card_async(thread_id))
        except Exception:
            logger.exception("timeout_card_failed", thread_id=thread_id)
        return {"status": "timeout", "thread_id": thread_id}


async def _send_timeout_card_async(message_id: str) -> None:
    """Send a timeout card replying to the original user message."""
    from app.graph.cards.templates import timeout_card
    from app.integrations.feishu.adapter import FeishuAdapter

    card = timeout_card(thread_id=message_id)
    try:
        await FeishuAdapter().reply_card(message_id, card)
    except Exception:
        logger.exception("timeout_card_send_failed", message_id=message_id)


async def _resume_graph_async(thread_id: str, chat_id: str) -> dict[str, Any]:
    from app.graph import get_or_init_graph

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}

    if chat_id and thread_id:
        try:
            import redis.asyncio as aioredis

            from app.config import get_settings as _gs

            r: aioredis.Redis = aioredis.from_url(_gs().REDIS_URL)  # type: ignore[no-untyped-call]
            async with r:
                await r.setex(f"active_task:{chat_id}", 600, thread_id)
        except Exception:
            logger.exception("active_task_register_failed", chat_id=chat_id)

    try:
        result = await graph.ainvoke(None, config=config)
        logger.info("graph_resumed", thread_id=thread_id, status=result.get("status"))
        _clear_active_task(chat_id, thread_id)
        return {"status": "completed", "thread_id": thread_id}
    except Exception as exc:
        logger.exception("graph_resume_failed", thread_id=thread_id, error=str(exc))
        _clear_active_task(chat_id, thread_id)
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


async def _handle_control_intent(msg: Any, control: str, graph: Any) -> dict[str, Any]:
    """Handle pause / resume / cancel messages directed at an active graph run."""
    import redis.asyncio as aioredis

    from app.config import get_settings

    try:
        settings = get_settings()
        async with aioredis.from_url(settings.REDIS_URL) as r:  # type: ignore[no-untyped-call]
            raw = await r.get(f"active_task:{msg.chat_id}")
        thread_id: str = raw.decode() if isinstance(raw, bytes) else (raw or "")
    except Exception:
        logger.exception("control_intent_redis_failed", chat_id=msg.chat_id)
        thread_id = ""

    if not thread_id:
        logger.info("no_active_task_for_control", chat_id=msg.chat_id, control=control)
        return {"status": "no_active_task"}

    config = {"configurable": {"thread_id": thread_id}}

    if control == "pause":
        try:
            await graph.aupdate_state(
                config, {"pending_user_action": "pause"}, as_node="step_router"
            )
            logger.info("pause_requested", thread_id=thread_id, chat_id=msg.chat_id)
        except Exception:
            logger.exception("pause_state_update_failed", thread_id=thread_id)
        return {"status": "pause_requested", "thread_id": thread_id}

    if control == "resume":
        try:
            await graph.aupdate_state(config, {"pending_user_action": None}, as_node="step_router")
            # Dispatch to slow queue — graph execution is long-running
            resume_graph_task.delay(thread_id, msg.chat_id or "")
            logger.info("resume_dispatched", thread_id=thread_id)
        except Exception:
            logger.exception("resume_failed", thread_id=thread_id)
        return {"status": "resumed", "thread_id": thread_id}

    if control == "cancel":
        from app.schemas.enums import TaskStatus

        try:
            await graph.aupdate_state(
                config,
                {"status": TaskStatus.cancelled, "pending_user_action": None},
                as_node="step_router",
            )
            # Dispatch cancel through slow queue so error_handler can clean up
            resume_graph_task.delay(thread_id, msg.chat_id or "")
            logger.info("cancel_dispatched", thread_id=thread_id)
        except Exception:
            logger.exception("cancel_failed", thread_id=thread_id)
        return {"status": "cancelled", "thread_id": thread_id}

    return {"status": "unknown_control"}


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


async def _handle_lego_command(msg: Any) -> dict[str, Any]:
    """Emit the lego scenario selector card in response to a /lego command."""
    from app.graph.cards.templates import lego_scenario_select_card
    from app.integrations.feishu.adapter import FeishuAdapter

    card = lego_scenario_select_card(thread_id=msg.message_id, chat_id=msg.chat_id)
    try:
        await FeishuAdapter().reply_card(msg.message_id, card)
    except Exception:
        logger.exception("lego_command_card_failed", message_id=msg.message_id)
    return {"status": "lego_card_sent", "message_id": msg.message_id}


async def _handle_lego_text(msg: Any, lego_scenarios: list[str]) -> dict[str, Any]:
    """Start a graph run with pre-set lego scenarios and user text as the goal."""
    from app.db.engine import get_session
    from app.graph import get_or_init_graph
    from app.repositories.task_repo import create_task
    from app.schemas.agent_state import make_agent_state
    from app.schemas.enums import OutputFormat, TaskType
    from app.schemas.intent import IntentSchema

    initial_state = make_agent_state(
        user_id=msg.sender_user_id,
        chat_id=msg.chat_id,
        message_id=msg.message_id,
    )
    initial_state["raw_input"] = msg.text
    initial_state["_lego_scenarios"] = lego_scenarios

    # Synthetic intent so step_router skips intent_parser but still runs context_retrieval
    formats = []
    if "C" in lego_scenarios:
        formats.append(OutputFormat.document)
    if "D" in lego_scenarios:
        formats.append(OutputFormat.presentation)
    initial_state["intent"] = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal=msg.text or "生成内容",
        output_formats=formats,
        ambiguity_score=0.0,
    )
    initial_state["normalized_text"] = msg.text or ""

    task_id: str = initial_state["task_id"]
    try:
        async with get_session() as session:
            await create_task(
                session,
                task_id=task_id,
                user_id=msg.sender_user_id,
                chat_id=msg.chat_id,
            )
    except Exception:
        logger.exception("lego_task_create_failed", task_id=task_id)

    config = {"configurable": {"thread_id": msg.message_id or ""}}
    try:
        graph = await get_or_init_graph()
        result = await graph.ainvoke(initial_state, config=config)
        logger.info("lego_graph_done", status=result.get("status"))
        return {"status": "completed", "message_id": msg.message_id}
    except Exception:
        logger.exception("lego_graph_failed", message_id=msg.message_id)
        return {"status": "error"}
