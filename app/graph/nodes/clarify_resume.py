"""clarify_resume node: consume pending_user_action, merge user answer into state."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)


@graph_node("clarify_resume")
async def clarify_resume_node(state: dict[str, Any]) -> dict[str, Any]:
    pending = state.get("pending_user_action") or {}
    request_id = pending.get("request_id", "unknown")

    clarify_answer: str = state.get("clarify_answer") or ""
    normalized_text: str = state.get("normalized_text", "")

    if clarify_answer:
        merged = f"{normalized_text}\n\n用户补充说明：{clarify_answer}".strip()
    else:
        merged = normalized_text

    logger.info(
        "clarify_resume",
        request_id=request_id,
        answer_len=len(clarify_answer),
    )

    return {
        "normalized_text": merged,
        "intent": None,  # force intent_parser to re-run with enriched text
        "pending_user_action": None,
        "clarify_answer": None,
        "status": TaskStatus.running,
    }
