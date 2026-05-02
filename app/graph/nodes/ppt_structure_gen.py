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
    doc = state.get("doc")

    primary_goal = getattr(intent, "primary_goal", "生成 PPT") if intent else "生成 PPT"
    target_audience = getattr(intent, "target_audience", None) if intent else None

    # In Lego flows (C→D), try to read the current Feishu doc content so PPT
    # reflects any edits the user may have made during a pause.
    fresh_doc_text = ""
    if doc and getattr(doc, "doc_id", None):
        try:
            from app.integrations.feishu.adapter import FeishuAdapter

            fresh_doc_text = await FeishuAdapter().get_doc_text(doc.doc_id)
            if fresh_doc_text:
                logger.info(
                    "ppt_structure_gen_fresh_doc",
                    doc_id=doc.doc_id,
                    chars=len(fresh_doc_text),
                )
        except Exception:
            logger.warning("ppt_structure_gen_doc_read_failed", doc_id=doc.doc_id)

    if fresh_doc_text:
        context_summary = fresh_doc_text[:2000]
    else:
        fallback = state.get("doc_markdown", "") or ""
        context_summary = (
            "\n".join(c.get("text", "")[:200] for c in context[:3])
            or fallback[:2000]
            or "（无背景资料）"
        )

    # Derive a reasonable slide count from content length instead of hardcoding 0.
    total_chars = sum(len(c.get("text", "")) for c in context[:3]) + len(
        fresh_doc_text or state.get("doc_markdown", "") or ""
    )
    if total_chars > 3000 or len(context) > 5:
        expected_slides = 10
    elif total_chars > 800:
        expected_slides = 7
    else:
        expected_slides = 5

    prompt_version = get_prompt("ppt_structure_gen")
    filled = prompt_version.text.format(
        primary_goal=primary_goal,
        target_audience=target_audience or "通用听众",
        expected_slides=expected_slides,
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
