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
    if has_time_word(normalized_text) and user_id:
        try:
            from app.integrations.feishu.calendar import FeishuCalendarClient

            client = FeishuCalendarClient()
            events = await client.get_events_around(user_id, normalized_text)
            calendar_context = format_events_for_prompt(events)
            logger.debug("calendar_context_fetched", event_count=len(events))
        except Exception:
            logger.warning("calendar_context_fetch_failed", user_id=user_id)
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

    llm = LLMService()
    try:
        intent: IntentSchema = await llm.structured(filled_prompt, IntentSchema, tier="pro")
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

    return {"intent": intent}
