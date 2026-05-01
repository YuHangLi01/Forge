"""doc_structure_gen node: generate document outline (Lite LLM)."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.doc_outline import DocOutline, DocOutlineSection
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

_FALLBACK_OUTLINE = DocOutline(
    document_title="文档",
    sections=[
        DocOutlineSection(id="s0", title="背景与目标"),
        DocOutlineSection(id="s1", title="核心内容"),
        DocOutlineSection(id="s2", title="总结与建议"),
    ],
)


@graph_node("doc_structure_gen")
async def doc_structure_gen_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.doc_structure  # noqa: F401
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.begin_node("📝 生成文档结构")

    intent = state.get("intent")
    context: list[dict[str, Any]] = state.get("retrieved_context") or []

    primary_goal = getattr(intent, "primary_goal", "生成文档") if intent else "生成文档"
    target_audience = getattr(intent, "target_audience", None) if intent else None
    style_hint = getattr(intent, "style_hint", None) if intent else None
    context_summary = "\n".join(c.get("text", "")[:150] for c in context[:3]) or "（无背景资料）"

    prompt_version = get_prompt("doc_structure_gen")
    filled = prompt_version.text.format(
        primary_goal=primary_goal,
        target_audience=target_audience or "通用读者",
        style_hint=style_hint or "专业、简洁",
        context_summary=context_summary,
    )

    llm = LLMService()
    try:
        outline: DocOutline = await llm.structured(filled, DocOutline, tier="lite")
        if not outline.sections:
            raise ValueError("empty outline")
    except Exception:
        logger.exception("doc_structure_gen_failed", fallback=True)
        outline = _FALLBACK_OUTLINE

    logger.info(
        "doc_outline_generated",
        title=outline.document_title,
        n_sections=len(outline.sections),
    )
    return {"doc_outline": outline.model_dump(), "completed_steps": ["doc_structure_gen"]}
