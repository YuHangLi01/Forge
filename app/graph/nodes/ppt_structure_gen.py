"""ppt_structure_gen node: generate PPT slide brief (Lite LLM)."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.ppt import PPTBriefSchema, SlideBrief

logger = structlog.get_logger(__name__)

_FALLBACK_BRIEF = PPTBriefSchema(
    title="演示文稿",
    target_audience="通用听众",
    slides=[
        SlideBrief(slide_index=0, page_type="cover", title="演示文稿"),
        SlideBrief(
            slide_index=1,
            page_type="content",
            title="核心内容",
            bullet_points=["要点一", "要点二", "要点三"],
        ),
        SlideBrief(slide_index=2, page_type="closing", title="谢谢"),
    ],
)


@graph_node("ppt_structure_gen")
async def ppt_structure_gen_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.ppt_structure  # noqa: F401  # registers PROMPT_V1
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    intent = state.get("intent")
    context: list[dict[str, Any]] = state.get("retrieved_context") or []

    primary_goal = getattr(intent, "primary_goal", "生成 PPT") if intent else "生成 PPT"
    target_audience = getattr(intent, "target_audience", None) if intent else None
    context_summary = "\n".join(c.get("text", "")[:200] for c in context[:3]) or "（无背景资料）"

    prompt_version = get_prompt("ppt_structure_gen")
    filled = prompt_version.text.format(
        primary_goal=primary_goal,
        target_audience=target_audience or "通用听众",
        expected_slides=0,
        context_summary=context_summary,
    )

    llm = LLMService()
    try:
        brief: PPTBriefSchema = await llm.structured(filled, PPTBriefSchema, tier="lite")
        if not brief.slides:
            raise ValueError("empty slide list")
    except Exception:
        logger.exception("ppt_structure_gen_failed", fallback=True)
        brief = _FALLBACK_BRIEF

    # Resolve design token from target_audience if not set by LLM
    if not brief.design_token_name:
        from app.services.design_tokens import resolve_token

        token = resolve_token(brief.target_audience)
        brief = brief.model_copy(update={"design_token_name": token.name})

    logger.info(
        "ppt_brief_generated",
        title=brief.title,
        n_slides=brief.slide_count,
        design_token=brief.design_token_name,
    )
    return {"ppt_brief": brief.model_dump(), "completed_steps": ["ppt_structure_gen"]}
