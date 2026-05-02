"""clarify_question node: generate ≤2 questions, emit card, pause graph."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)


@graph_node("clarify_question")
async def clarify_question_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.clarify_question  # noqa: F401  # registers PROMPT_V1
    from app.graph.cards.templates import clarify_card
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    chat_id: str = state.get("chat_id", "")
    message_id: str = state.get("message_id", "")
    normalized_text: str = state.get("normalized_text", "")
    intent = state.get("intent")

    intent_summary = ""
    if intent is not None:
        task_type = getattr(intent, "task_type", "")
        goal = getattr(intent, "primary_goal", "")
        intent_summary = f"任务类型={task_type}, 目标={goal}"

    prompt_version = get_prompt("clarify_question")
    filled = prompt_version.text.format(
        user_message=normalized_text,
        intent_summary=intent_summary or "（尚未解析）",
    )

    llm = LLMService()
    try:
        raw: str = await llm.invoke(filled, tier="lite")
        questions = [line.strip() for line in raw.strip().splitlines() if line.strip()][:2]
    except Exception:
        logger.exception("clarify_question_llm_failed")
        questions = ["请问您具体希望完成什么任务？", "有什么特别的要求或限制吗？"]

    if not questions:
        questions = ["请问您具体希望完成什么任务？"]

    # thread_id mirrors what message_tasks uses
    thread_id = message_id

    request_id = str(uuid4())
    card = clarify_card(questions, request_id=request_id, thread_id=thread_id)

    # Store pending clarify metadata in Redis (for TTL cleanup)
    try:
        import redis.asyncio as aioredis

        from app.config import get_settings

        settings = get_settings()
        r: aioredis.Redis = aioredis.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]
        payload = json.dumps(
            {
                "thread_id": thread_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "request_id": request_id,
                "waiting_since": time.time(),
            }
        )
        async with r:
            await r.setex(f"clarify:{request_id}", 7200, payload)  # 2h TTL as safety net
    except Exception:
        logger.warning("clarify_redis_store_failed", request_id=request_id)

    # Reply to the original user message with an interactive clarify card.
    # update_card would fail (error 230001) because the original message is plain text.
    try:
        feishu = FeishuAdapter()
        if message_id:
            await feishu.reply_card(message_id, card)
        else:
            await feishu.send_text(chat_id, json.dumps(card))
        logger.info(
            "clarify_card_sent",
            chat_id=chat_id,
            request_id=request_id,
            questions=questions,
        )
    except Exception:
        logger.exception("clarify_card_send_failed")

    return {
        "pending_user_action": {
            "kind": "clarify",
            "request_id": request_id,
            "waiting_since": time.time(),
            "chat_id": chat_id,
            "message_id": message_id,
        },
        "clarify_count": (state.get("clarify_count") or 0) + 1,
        "status": TaskStatus.waiting_human,
    }
