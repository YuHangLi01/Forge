"""mid_execution_replanner node: evaluate doc quality and optionally insert an extra PPT slide."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)


@graph_node("mid_execution_replanner")
async def mid_execution_replanner_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.schemas.replan import ReplanDecision
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)

    ppt_brief: dict[str, Any] | None = state.get("ppt_brief")
    context: list[dict[str, Any]] = state.get("retrieved_context") or []

    # If there's no brief yet, skip gracefully
    if not ppt_brief:
        logger.info("mid_execution_replanner_skip", reason="no_ppt_brief")
        pb.update_thinking("📋 无PPT大纲，跳过重规划。")
        return {"completed_steps": ["mid_execution_replanner"]}

    slides: list[dict[str, Any]] = ppt_brief.get("slides") or []

    # Find the most relevant unused context chunk (beyond the first 3 already used)
    if len(context) > 3:
        unused_chunk: dict[str, Any] = context[3]
    elif context:
        unused_chunk = context[-1]
    else:
        unused_chunk = {}
    unused_context = unused_chunk.get("text", "")[:500] if unused_chunk else ""

    # Build a brief ppt outline summary
    ppt_brief_summary = "\n".join(
        f"  {i}. {s.get('title', '')} ({s.get('page_type', '')})" for i, s in enumerate(slides)
    )

    if not unused_context:
        logger.info("mid_execution_replanner_skip", reason="no_unused_context")
        pb.update_thinking("📋 无未使用的背景资料，跳过重规划。")
        return {"completed_steps": ["mid_execution_replanner"]}

    prompt = (
        "文档已生成。以下是未充分利用的背景资料片段：\n"
        f"{unused_context}\n\n"
        "当前PPT大纲：\n"
        f"{ppt_brief_summary}\n\n"
        "请判断：是否应该在PPT中增加一页来更好地呈现上述资料？\n"
        "如果是，请给出新幻灯片的标题和要点（不超过3条）。\n"
        '请以JSON回复：{"should_add": true/false, "slide_title": "...",'
        ' "bullet_points": ["...", "..."]}'
    )

    llm = LLMService()
    try:
        decision: ReplanDecision = await llm.structured(prompt, ReplanDecision, tier="lite")
    except Exception:
        logger.exception("mid_execution_replanner_llm_failed")
        pb.update_thinking("⚠️ 重规划判断失败，保持原PPT大纲。")
        return {"completed_steps": ["mid_execution_replanner"]}

    if not decision.should_add:
        logger.info("mid_execution_replanner_no_change", reason="llm_decided_no")
        pb.update_thinking("✅ 重规划决策：PPT大纲已充分覆盖背景资料，无需修改。")
        return {"ppt_brief": ppt_brief, "completed_steps": ["mid_execution_replanner"]}

    # Insert a new SlideBrief at index 2 (after intro slides)
    insert_at = min(2, len(slides))
    new_slide: dict[str, Any] = {
        "slide_index": insert_at,
        "page_type": "content",
        "title": decision.slide_title or "补充背景资料",
        "bullet_points": decision.bullet_points[:3],
        "speaker_notes": "",
    }

    updated_slides = list(slides)
    updated_slides.insert(insert_at, new_slide)

    # Re-index all slides so slide_index matches position
    for idx, slide in enumerate(updated_slides):
        slide["slide_index"] = idx

    updated_brief = dict(ppt_brief)
    updated_brief["slides"] = updated_slides

    logger.info(
        "mid_execution_replanner_inserted_slide",
        title=new_slide["title"],
        insert_at=insert_at,
        total_slides=len(updated_slides),
    )
    pb.update_thinking(
        f"🔄 重规划：已插入补充幻灯片「{new_slide['title']}」（共 {len(updated_slides)} 页）。"
    )

    return {"ppt_brief": updated_brief, "completed_steps": ["mid_execution_replanner"]}
