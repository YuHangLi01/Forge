"""delivery_node: final node — battle report card, wiki archive, ChromaDB write-back."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)


def _extract_mention_user_ids(retrieved_context: list[dict[str, Any]]) -> list[str]:
    """Extract distinct user_ids mentioned in retrieved_context metadata."""
    seen: set[str] = set()
    ids: list[str] = []
    for chunk in retrieved_context or []:
        meta = chunk.get("metadata") or {}
        uid: str = meta.get("sender_user_id") or meta.get("user_id") or ""
        if uid and uid not in seen:
            seen.add(uid)
            ids.append(uid)
    return ids[:5]  # cap to avoid spammy @mention lines


@graph_node("delivery_node")
async def delivery_node_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.graph.cards.templates import battle_report_card
    from app.integrations.feishu.adapter import FeishuAdapter

    message_id: str = state.get("message_id", "")
    chat_id: str = state.get("chat_id", "")
    user_id: str = state.get("user_id", "")
    task_id: str = state.get("task_id", "")

    doc = state.get("doc")
    ppt = state.get("ppt")
    completed_steps = set(state.get("completed_steps") or [])
    retrieved_context: list[dict[str, Any]] = state.get("retrieved_context") or []

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

    # ── Wiki archival (async, non-blocking) ──────────────────────────────────
    wiki_url: str | None = None
    try:
        from app.integrations.feishu.wiki import FeishuWikiClient

        wiki_client = FeishuWikiClient()
        title = doc_title or ppt_title or "任务产物归档"
        doc_token: str | None = getattr(doc, "doc_id", None) if doc else None
        node_token = await wiki_client.create_node(title=title, doc_token=doc_token)
        if node_token:
            wiki_url = wiki_client.share_url(node_token)
            logger.info("delivery_wiki_archived", node_token=node_token)
    except Exception:
        logger.warning("delivery_wiki_archive_failed", exc_info=True)

    # ── ChromaDB write-back (fire-and-forget) ────────────────────────────────
    if user_id and task_id:
        try:
            import asyncio

            from app.services.artifact_indexer import ArtifactIndexer

            goal: str = getattr(state.get("intent"), "primary_goal", "") or ""
            summary = f"{doc_title or ''} {ppt_title or ''} {goal}".strip()
            asyncio.ensure_future(
                ArtifactIndexer().index_delivery(
                    user_id=user_id,
                    task_id=task_id,
                    doc=doc,
                    ppt=ppt,
                    task_summary=summary,
                )
            )
        except Exception:
            logger.warning("delivery_artifact_indexer_failed", exc_info=True)

    # ── Build and send battle report card ────────────────────────────────────
    mention_user_ids = _extract_mention_user_ids(retrieved_context)
    has_both = bool(doc_url and ppt_url)
    if has_both or is_partial or wiki_url:
        card = battle_report_card(
            doc_url=doc_url,
            doc_title=doc_title,
            ppt_url=ppt_url,
            ppt_title=ppt_title,
            is_partial=is_partial,
            mention_user_ids=mention_user_ids or None,
            wiki_url=wiki_url,
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
        wiki_url=wiki_url,
        mention_count=len(mention_user_ids),
    )
    return {"completed_steps": ["delivery_node"], "status": TaskStatus.completed}
