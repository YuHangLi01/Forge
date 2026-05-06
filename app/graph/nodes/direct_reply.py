"""direct_reply node: send a conversational reply without creating any documents.

Handles task_type="chat" (greetings, chitchat, thanks) and
task_type="query_only" when the intent is already clear and no
planning is required.  Calls the LLM for a short friendly response
and sends it back via FeishuAdapter, then marks the task completed.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "你是 Forge 飞书智能办公助手。"
    "用简短、友好的中文直接回复用户消息，不超过三句话，不要主动推销功能。"
)


@graph_node("direct_reply")
async def direct_reply_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    chat_id: str = state.get("chat_id", "")
    normalized_text: str = state.get("normalized_text", "")

    llm = LLMService()
    try:
        reply = await llm.invoke(
            f"{_SYSTEM}\n\n用户消息：{normalized_text}",
            tier="lite",
        )
        reply = reply.strip()
    except Exception:
        logger.exception("direct_reply_llm_failed")
        reply = "你好！有什么我可以帮你的吗？"

    try:
        feishu = FeishuAdapter()
        if message_id:
            await feishu.reply_text(message_id, reply)
        else:
            await feishu.send_text(chat_id, reply)
    except Exception:
        logger.exception("direct_reply_send_failed")

    logger.info("direct_reply_done", text_len=len(reply))
    return {
        "status": TaskStatus.completed,
        "completed_steps": ["direct_reply"],
    }
