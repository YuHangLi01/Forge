"""prior_artifact_retrieval: find delivered artifacts from ChromaDB for cross-session modification.

Triggered when the user references a previous task ("上次给VP看的") in a new session
where state["ppt"] and state["doc"] are both None.  Queries ChromaDB with
``source=delivered`` to reconstruct the PPT artifact, then sends a confirmation
card so the user can verify before the modification flow continues.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.artifacts import PPTArtifact, SlideSchema
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

_TOP_K = 20


@graph_node("prior_artifact_retrieval")
async def prior_artifact_retrieval_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.graph.cards.templates import prior_artifact_confirm_card
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.chroma_service import ChromaService

    user_id: str = state.get("user_id", "")
    message_id: str = state.get("message_id", "")
    intent = state.get("intent")
    normalized_text: str = state.get("normalized_text", "")

    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.begin_node('🤔 让我看看你说的"上次"')

    query: str = getattr(intent, "primary_goal", "") or normalized_text

    pb.emit_tool_use(
        "历史检索（ChromaDB）",
        f"user={user_id}, query={query[:30]}, filter=source:delivered",
    )

    try:
        svc = ChromaService()
        results = await svc.query(
            user_id=user_id,
            query_text=query,
            n_results=_TOP_K,
            extra_where={"source": "delivered"},
        )
    except Exception:
        logger.exception("prior_artifact_retrieval_failed")
        results = []

    if not results:
        pb.emit_tool_use(
            "历史检索（ChromaDB）",
            f"query={query[:30]}",
            "未找到已交付产物",
        )
        return {"completed_steps": ["prior_artifact_retrieval"]}

    # Group PPT slide chunks by ppt_id; pick the ppt_id with the most hits.
    ppt_chunks: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        meta = r.get("metadata", {})
        ppt_id = meta.get("ppt_id", "")
        if ppt_id and meta.get("chunk_type") == "ppt_slide":
            ppt_chunks.setdefault(ppt_id, []).append(r)

    if not ppt_chunks:
        pb.emit_tool_use(
            "历史检索（ChromaDB）",
            f"query={query[:30]}",
            "未找到 PPT 类型产物",
        )
        return {"completed_steps": ["prior_artifact_retrieval"]}

    best_ppt_id = max(ppt_chunks, key=lambda k: len(ppt_chunks[k]))
    best_chunks = sorted(
        ppt_chunks[best_ppt_id],
        key=lambda r: r["metadata"].get("slide_index", 0),
    )

    first_meta = best_chunks[0]["metadata"]
    ppt_title: str = first_meta.get("ppt_title", "PPT 文档")
    share_url: str = first_meta.get("share_url", "")
    task_id: str = first_meta.get("task_id", "")

    pb.emit_tool_use(
        "历史检索（ChromaDB）",
        f"query={query[:30]}, filter=source:delivered",
        f'命中 "{ppt_title}"（{len(best_chunks)} 页）',
    )

    # Reconstruct PPTArtifact from the stored chunk text and metadata.
    slides: list[SlideSchema] = []
    for chunk in best_chunks:
        meta = chunk["metadata"]
        idx: int = int(meta.get("slide_index", 0))
        slide_title: str = meta.get("slide_title", f"第{idx + 1}页")
        text: str = chunk.get("text", "")
        bullets = [line[2:] for line in text.splitlines() if line.startswith("• ")]
        slides.append(SlideSchema(page_index=idx, title=slide_title, bullets=bullets))

    prior_ppt = PPTArtifact(
        ppt_id=best_ppt_id,
        title=ppt_title,
        slides=slides,
        share_url=share_url,
    )

    # Send confirmation card — user must click [✅ 是的] to proceed.
    card = prior_artifact_confirm_card(
        title=ppt_title,
        share_url=share_url,
        slide_count=len(slides),
        task_id=task_id,
        message_id=message_id,
    )
    try:
        if message_id:
            await FeishuAdapter().reply_card(message_id, card)
    except Exception:
        logger.exception("prior_artifact_confirm_card_failed", message_id=message_id)

    return {
        "ppt": prior_ppt,
        "pending_user_action": {
            "kind": "confirm_prior_artifact",
            "task_id": task_id,
            "ppt_id": best_ppt_id,
            "ppt_title": ppt_title,
        },
        "completed_steps": ["prior_artifact_retrieval"],
    }
