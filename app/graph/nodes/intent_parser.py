"""intent_parser node: parse normalized_text into IntentSchema."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.intent import IntentSchema
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

_FALLBACK_INTENT = IntentSchema(
    task_type="create_new",
    primary_goal="用户意图解析失败，需要澄清",
    output_formats=["message_only"],
    ambiguity_score=1.0,
    missing_info=["解析失败，请重新描述您的需求"],
)


@graph_node("intent_parser")
async def intent_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.intent_parser as _ip_prompts  # noqa: F401  # registers PROMPT_V1/V2
    from app.prompts._versioning import get as get_prompt
    from app.services.calendar_context import format_events_for_prompt, has_time_word
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    user_id: str = state.get("user_id", "")
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.begin_node("🧠 理解意图")

    normalized_text: str = state.get("normalized_text", "")

    # Fetch calendar context when the message contains time references.
    calendar_context = ""
    events: list[Any] = []
    if has_time_word(normalized_text) and user_id:
        from app.db.engine import get_session
        from app.integrations.feishu.calendar import CalendarFetchError, FeishuCalendarClient
        from app.integrations.feishu.oauth import get_auth_url

        try:
            pb.emit_tool_use("飞书日历查询", f"date_hint={normalized_text[:20]}")
            client = FeishuCalendarClient()
            async with get_session() as db:
                events = await client.get_events_around(user_id, normalized_text, db)
            calendar_context = format_events_for_prompt(events)
            pb.emit_tool_use("飞书日历查询", f"返回 {len(events)} 个相关日程")
            logger.debug("calendar_context_fetched", event_count=len(events))

        except CalendarFetchError as exc:
            calendar_context = ""
            logger.info("calendar_context_unavailable", user_id=user_id, reason=str(exc))
            unauthorized = "未完成飞书日历授权" in str(exc)
            pb.emit_tool_use(
                "飞书日历查询",
                f"date_hint={normalized_text[:20]}",
                (
                    "未授权，已发送授权链接，等待授权完成…"
                    if unauthorized
                    else f"调用失败：{str(exc)[:60]}"
                ),
            )
            if unauthorized and message_id:
                try:
                    from app.integrations.feishu.adapter import FeishuAdapter
                    from app.services.oauth_pause import mark_oauth_pending

                    chat_id_from_state: str = state.get("chat_id", "")
                    await mark_oauth_pending(user_id, message_id, chat_id_from_state)

                    auth_url = get_auth_url(user_id)
                    await FeishuAdapter().reply_text(
                        message_id,
                        "检测到您的消息涉及日程安排，请先授权 Forge 读取您的飞书日历：\n"
                        f"{auth_url}\n"
                        "授权完成后会自动继续处理您的请求，无需重新发送。",
                    )
                    logger.info("calendar_auth_link_sent", user_id=user_id)

                    # Pause graph until OAuth callback resumes via resume_graph_task.
                    # _FALLBACK_INTENT is a placeholder — it will be cleared by the
                    # OAuth callback's aupdate_state(intent=None) before resume.
                    return {
                        "intent": _FALLBACK_INTENT,
                        "pending_user_action": {
                            "kind": "oauth_wait",
                            "thread_id": message_id,
                            "request_id": message_id,
                        },
                    }
                except Exception:
                    logger.warning("calendar_auth_link_send_failed", user_id=user_id, exc_info=True)

        except Exception as exc:
            logger.warning("calendar_context_fetch_failed", user_id=user_id, exc_info=True)
            pb.emit_tool_use(
                "飞书日历查询",
                f"date_hint={normalized_text[:20]}",
                f"调用失败：{str(exc)[:60]}",
            )
            calendar_context = ""

    # Use V2 prompt when calendar context is available; fall back to V1.
    if calendar_context:
        from app.prompts.intent_parser import PROMPT_V2

        filled_prompt = PROMPT_V2.text.format(
            user_message=normalized_text, calendar_context=calendar_context
        )
        prompt_version_name = "v2"
    else:
        prompt_version = get_prompt("intent_parser")
        filled_prompt = prompt_version.text.format(user_message=normalized_text)
        prompt_version_name = prompt_version.version

    # error_handler may set _force_tier="lite" for degraded retry runs
    llm_tier: str = state.get("_force_tier") or "pro"
    llm = LLMService()
    try:
        intent: IntentSchema = await llm.structured(filled_prompt, IntentSchema, tier=llm_tier)  # type: ignore[arg-type]
        logger.info(
            "intent_parsed",
            task_type=intent.task_type,
            ambiguity_score=intent.ambiguity_score,
            prompt_version=prompt_version_name,
            calendar_context_used=bool(calendar_context),
        )
    except Exception:
        logger.exception("intent_parser_llm_failed", fallback=True)
        intent = _FALLBACK_INTENT

    # Emit a calendar clarify card when the intent is ambiguous and multiple events exist.
    # Skip if user already answered a clarify round (normalized_text now carries
    # "用户补充说明：…" via clarify_resume); re-emitting would loop forever.
    already_clarified = "用户补充说明：" in normalized_text
    if (
        calendar_context
        and intent.ambiguity_score >= 0.7
        and len(events) >= 2
        and not already_clarified
    ):
        try:
            from app.graph.cards.templates import calendar_clarify_card
            from app.integrations.feishu.adapter import FeishuAdapter

            events_as_dicts = [
                {"summary": e.summary, "start_time": e.start_time, "end_time": e.end_time}
                for e in events
            ]
            card = calendar_clarify_card(events_as_dicts, thread_id=message_id)
            await FeishuAdapter().reply_card(message_id, card)
            logger.info("calendar_clarify_card_sent", event_count=len(events))
        except Exception:
            logger.warning("calendar_clarify_card_failed", exc_info=True)

        return {
            "intent": intent,
            "pending_user_action": {
                "kind": "clarify",
                "thread_id": message_id,
                "request_id": message_id,
            },
        }

    return {"intent": intent}
