"""context_retrieval node: query ChromaDB with strict user_id isolation.

Retrieves relevant context chunks for the current intent's primary_goal.
- Modify path: returns [] immediately (context is already in the document).
- All queries are filtered by user_id; no cross-user data leakage is possible.
- Chroma errors degrade gracefully to empty list (does not raise).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskType
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

_TOP_K = 5


@graph_node("context_retrieval")
async def context_retrieval_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent")
    user_id: str = state.get("user_id", "")
    message_id: str = state.get("message_id", "")
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.begin_node("📚 检索背景资料")

    # Modification path: existing doc context is sufficient; skip retrieval.
    if intent is not None and getattr(intent, "task_type", None) == TaskType.modify_existing:
        logger.debug("context_retrieval_skipped_modify_path")
        return {"retrieved_context": [], "completed_steps": ["context_retrieval"]}

    query: str = ""
    if intent is not None:
        query = getattr(intent, "primary_goal", "") or ""
    if not query:
        query = state.get("normalized_text", "")

    if not query.strip():
        logger.info("context_retrieval_empty_query")
        return {"retrieved_context": [], "completed_steps": ["context_retrieval"]}

    try:
        from app.services.chroma_service import ChromaService

        pb.emit_tool_use("历史检索（ChromaDB）", f"query={query[:30]}")
        # Embed with our bge-base-zh-v1.5 (768-dim) — must match indexed vectors.
        # Wrapped separately so a missing ML dep (e.g. CI without --extra ml)
        # falls through to ChromaDB's default embedder rather than aborting
        # the whole retrieval.
        query_embedding: list[float] | None = None
        try:
            from app.services.embedding_service import EmbeddingService

            query_embedding = await EmbeddingService().embed(query)
        except Exception:
            logger.warning("embedding_service_unavailable", exc_info=True)

        svc = ChromaService()
        results = await svc.query(
            user_id=user_id,
            query_text=query,
            query_embedding=query_embedding,
            n_results=_TOP_K,
        )
        top_summary = results[0]["text"][:60] if results else "无结果"
        pb.emit_tool_use(
            "历史检索（ChromaDB）",
            f"query={query[:30]}",
            f"返回 {len(results)} 条，Top-1：{top_summary}…",
        )
        logger.info(
            "context_retrieved",
            user_id=user_id,
            query_len=len(query),
            result_count=len(results),
        )
    except Exception:
        logger.exception("context_retrieval_failed", user_id=user_id)
        results = []

    return {"retrieved_context": results, "completed_steps": ["context_retrieval"]}
