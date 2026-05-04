"""delivery_node: final node that emits a consolidated battle report card."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)


@graph_node("delivery_node")
async def delivery_node_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.graph.cards.templates import battle_report_card
    from app.integrations.feishu.adapter import FeishuAdapter

    message_id: str = state.get("message_id", "")
    chat_id: str = state.get("chat_id", "")

    doc = state.get("doc")
    ppt = state.get("ppt")
    completed_steps = set(state.get("completed_steps") or [])

    doc_url: str | None = getattr(doc, "share_url", None) if doc else None
    doc_title: str | None = getattr(doc, "title", None) if doc else None
    ppt_url: str | None = getattr(ppt, "share_url", None) if ppt else None
    ppt_title: str | None = getattr(ppt, "title", None) if ppt else None

    # Detect partial completion (e.g. C+D where PPT write failed)
    plan = state.get("plan")
    is_partial = False
    if plan:
        all_steps = {s.node_name for s in plan.steps}
        is_partial = bool(all_steps - completed_steps - {"delivery_node"})

    # Only send a consolidated card when there are multiple artifacts or a partial result.
    # For single-artifact tasks the individual emit_artifact card from the write node suffices.
    has_both = bool(doc_url and ppt_url)
    if has_both or is_partial:
        card = battle_report_card(
            doc_url=doc_url,
            doc_title=doc_title,
            ppt_url=ppt_url,
            ppt_title=ppt_title,
            is_partial=is_partial,
        )
        try:
            adapter = FeishuAdapter()
            if message_id:
                await adapter.reply_card(message_id, card)
            elif chat_id:
                await adapter.send_card(chat_id, card)
        except Exception:
            logger.exception("delivery_node_card_failed", message_id=message_id)

    logger.info(
        "delivery_node_done",
        has_doc=bool(doc_url),
        has_ppt=bool(ppt_url),
        is_partial=is_partial,
    )
    return {"completed_steps": ["delivery_node"], "status": TaskStatus.completed}
