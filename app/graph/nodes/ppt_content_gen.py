"""ppt_content_gen node: generate per-slide content concurrently (Semaphore 3).

Supports breakpoint resume: slides in state["completed_slide_ids"] are skipped.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node

logger = structlog.get_logger(__name__)

_SEMAPHORE = asyncio.Semaphore(3)


def _build_slide_titles_summary(slides: list[dict[str, Any]]) -> str:
    return " | ".join(
        f"{s.get('slide_index', i)}. {s.get('title', '')}" for i, s in enumerate(slides)
    )


async def _gen_slide_content(
    slide: dict[str, Any],
    ppt_title: str,
    target_audience: str,
    slide_titles_summary: str,
    llm: Any,
) -> dict[str, Any]:
    from app.prompts.ppt_content import PAGE_TYPE_PROMPTS

    page_type: str = slide.get("page_type", "content")
    template = PAGE_TYPE_PROMPTS.get(page_type, PAGE_TYPE_PROMPTS["content"])

    filled = template.format(
        title=slide.get("title", ""),
        bullet_points="\n".join(f"- {b}" for b in slide.get("bullet_points", [])),
        speaker_notes=slide.get("speaker_notes", ""),
        ppt_title=ppt_title,
        target_audience=target_audience,
        slide_titles_summary=slide_titles_summary,
    )

    async with _SEMAPHORE:
        try:
            raw: str = await llm.invoke(filled, tier="lite")
            # Strip markdown code fence if present
            stripped = raw.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            content: dict[str, Any] = json.loads(stripped)
        except Exception:
            logger.exception(
                "ppt_content_gen_slide_failed",
                slide_index=slide.get("slide_index"),
                page_type=page_type,
            )
            content = {
                "heading": slide.get("title", ""),
                "bullets": slide.get("bullet_points", []),
                "speaker_notes": "",
            }

    return {
        "slide_index": slide.get("slide_index", 0),
        "page_type": page_type,
        "title": slide.get("title", ""),
        "content": content,
    }


@graph_node("ppt_content_gen")
async def ppt_content_gen_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.services.llm_service import LLMService

    raw_brief: dict[str, Any] = state.get("ppt_brief") or {}
    ppt_title: str = raw_brief.get("title", "演示文稿")
    target_audience: str = raw_brief.get("target_audience", "通用听众")
    slides: list[dict[str, Any]] = raw_brief.get("slides") or []
    completed_slide_ids: list[int] = state.get("completed_slide_ids") or []

    slide_titles_summary = _build_slide_titles_summary(slides)
    llm = LLMService()

    existing_slides: dict[int, dict[str, Any]] = {}
    for existing in state.get("ppt_slides") or []:
        existing_slides[existing.get("slide_index", -1)] = existing

    async def _process_slide(slide: dict[str, Any]) -> dict[str, Any]:
        idx = slide.get("slide_index", -1)
        if idx in completed_slide_ids:
            logger.debug("ppt_content_gen_skip", slide_index=idx)
            return existing_slides.get(idx, slide)

        return await _gen_slide_content(
            slide, ppt_title, target_audience, slide_titles_summary, llm
        )

    results = await asyncio.gather(*[_process_slide(s) for s in slides])
    slide_list = sorted(results, key=lambda s: s.get("slide_index", 0))

    logger.info("ppt_content_gen_done", n_slides=len(slide_list))
    return {"ppt_slides": slide_list}
