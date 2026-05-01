"""doc_content_gen node: generate section content concurrently (Semaphore 3)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.artifacts import DocArtifact, DocSection
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

_SEMAPHORE = asyncio.Semaphore(3)


@graph_node("doc_content_gen")
async def doc_content_gen_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.doc_content  # noqa: F401
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)

    raw_outline: dict[str, Any] = state.get("doc_outline") or {}
    doc_title: str = raw_outline.get("document_title", "文档")
    section_dicts: list[dict[str, Any]] = raw_outline.get("sections") or []

    intent = state.get("intent")
    context: list[dict[str, Any]] = state.get("retrieved_context") or []
    completed_section_ids: list[str] = state.get("completed_section_ids") or []

    primary_goal = getattr(intent, "primary_goal", "") if intent else ""
    target_audience = getattr(intent, "target_audience", None) if intent else None
    style_hint = getattr(intent, "style_hint", None) if intent else None
    context_summary = "\n".join(c.get("text", "")[:150] for c in context[:3]) or "（无背景资料）"
    all_titles = ", ".join(s.get("title", "") for s in section_dicts)

    prompt_version = get_prompt("doc_content_gen")
    llm = LLMService()

    async def _gen_section(sec: dict[str, Any]) -> DocSection:
        sec_id = sec.get("id", "?")
        sec_title = sec.get("title", "")

        if sec_id in completed_section_ids:
            logger.debug("doc_content_gen_skip", section_id=sec_id)
            existing_doc: DocArtifact | None = state.get("doc")
            if existing_doc:
                for s in existing_doc.sections:
                    if s.id == sec_id:
                        return s
            return DocSection(id=sec_id, title=sec_title, content_md="")

        pb.begin_node(f"✍️ 正在撰写「{sec_title}」")

        filled = prompt_version.text.format(
            doc_title=doc_title,
            section_title=sec_title,
            primary_goal=primary_goal,
            target_audience=target_audience or "通用读者",
            style_hint=style_hint or "专业、简洁",
            context_summary=context_summary,
            all_section_titles=all_titles,
        )

        async with _SEMAPHORE:
            try:
                content_md: str = await llm.invoke(filled, tier="lite")
            except Exception:
                logger.exception("doc_content_gen_section_failed", section_id=sec_id)
                content_md = f"{sec_title}内容生成失败，请重试。"

        logger.debug("doc_content_gen_section_done", section_id=sec_id, chars=len(content_md))
        return DocSection(id=sec_id, title=sec_title, content_md=content_md.strip())

    sections = await asyncio.gather(*[_gen_section(s) for s in section_dicts])

    # Build full markdown for feishu_doc_write to consume
    full_md = "\n\n".join(f"# {s.title}\n\n{s.content_md}" for s in sections)

    doc = DocArtifact(doc_id="", title=doc_title, sections=list(sections))

    logger.info("doc_content_gen_done", n_sections=len(sections), total_chars=len(full_md))
    return {"doc": doc, "doc_markdown": full_md}
