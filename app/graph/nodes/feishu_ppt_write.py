"""feishu_ppt_write node: render .pptx, upload to Feishu Drive, emit artifact card."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.artifacts import SlideSchema
from app.schemas.enums import SlideLayout, TaskStatus

logger = structlog.get_logger(__name__)

_PAGE_TYPE_TO_LAYOUT: dict[str, SlideLayout] = {
    "cover": SlideLayout.cover,
    "agenda": SlideLayout.title_content,
    "section_header": SlideLayout.section_header,
    "content": SlideLayout.title_content,
    "closing": SlideLayout.blank,
}


def _coerce_bullets(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(b.get("text", b)) if isinstance(b, dict) else str(b) for b in value]
    return [str(value)]


def _raw_to_slide_schema(raw: dict[str, Any]) -> SlideSchema:
    """Convert a ppt_content_gen output dict to a SlideSchema."""
    content: dict[str, Any] = raw.get("content") or {}
    page_type: str = raw.get("page_type", "content")
    layout = _PAGE_TYPE_TO_LAYOUT.get(page_type, SlideLayout.title_content)
    title: str = content.get("heading") or raw.get("title", "")

    if page_type == "agenda":
        bullets = _coerce_bullets(content.get("items"))
    elif page_type in ("cover", "closing"):
        sub = content.get("subheading") or ""
        bullets = [sub] if sub else []
    elif page_type == "section_header":
        tag = content.get("tagline") or ""
        bullets = [tag] if tag else []
    else:
        bullets = _coerce_bullets(content.get("bullets"))

    return SlideSchema(
        page_index=raw.get("slide_index", 0),
        layout=layout,
        title=title,
        bullets=bullets,
        speaker_notes=content.get("speaker_notes", ""),
    )


@graph_node("feishu_ppt_write")
async def feishu_ppt_write_node(state: dict[str, Any]) -> dict[str, Any]:
    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.ppt_service import PPTService
    from app.services.progress_broadcaster import ProgressBroadcaster

    message_id: str = state.get("message_id", "")
    chat_id: str = state.get("chat_id", "")

    raw_slides: list[dict[str, Any]] = state.get("ppt_slides") or []
    raw_brief: dict[str, Any] = state.get("ppt_brief") or {}
    title: str = raw_brief.get("title", "演示文稿")
    token_name: str = raw_brief.get("design_token_name", "minimal")

    if not raw_slides:
        logger.error("feishu_ppt_write_no_slides", message_id=message_id)
        return {"error": "ppt_slides 为空，无法生成 PPT", "status": TaskStatus.failed}

    slides = [_raw_to_slide_schema(s) for s in raw_slides]

    adapter = FeishuAdapter()
    svc = PPTService(adapter=adapter)
    ppt_artifact = await svc.create_from_outline(title, slides, token_name=token_name)

    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    if ppt_artifact.share_url:
        pb.emit_artifact(label=title, url=ppt_artifact.share_url)
    else:
        logger.warning("feishu_ppt_write_no_share_url", title=title)

    if chat_id and ppt_artifact.ppt_id:
        try:
            settings = get_settings()
            async with aioredis.from_url(settings.REDIS_URL) as r:  # type: ignore[no-untyped-call]
                await r.setex(f"active_ppt:{chat_id}", 3600, ppt_artifact.model_dump_json())
        except Exception:
            logger.exception("feishu_ppt_write_cache_failed", chat_id=chat_id)

    logger.info(
        "feishu_ppt_write_done",
        title=title,
        slide_count=len(slides),
        ppt_id=ppt_artifact.ppt_id,
    )
    return {
        "ppt": ppt_artifact,
        "status": TaskStatus.completed,
        "completed_steps": ["feishu_ppt_write"],
    }
