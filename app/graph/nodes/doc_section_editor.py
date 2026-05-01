"""doc_section_editor node: rewrite a specific section and record the change."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.modification import ModificationRecord
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

_MAX_HISTORY = 50


@graph_node("doc_section_editor")
async def doc_section_editor_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.begin_node("✏️ 修改文档章节")

    mod_intent = state.get("mod_intent")
    doc = state.get("doc")
    modification_history: list[ModificationRecord] = list(state.get("modification_history") or [])

    if mod_intent is None or doc is None:
        logger.warning("doc_section_editor_missing_mod_intent_or_doc")
        return {}

    scope_identifier: str = getattr(mod_intent, "scope_identifier", "")
    instruction: str = getattr(mod_intent, "instruction", "")
    step_index = len(modification_history)

    # Find the target section by title match (case-insensitive)
    target_section = None
    for section in getattr(doc, "sections", []):
        if section.title.strip().lower() == scope_identifier.strip().lower():
            target_section = section
            break
    # Fallback: partial match
    if target_section is None:
        for section in getattr(doc, "sections", []):
            if scope_identifier.strip().lower() in section.title.strip().lower():
                target_section = section
                break

    if target_section is None:
        logger.warning("doc_section_editor_section_not_found", scope=scope_identifier)
        return {}

    before_summary = target_section.content_md[:200]

    # Generate new content
    prompt = (
        f"请根据以下修改指令，重写文档章节《{target_section.title}》的内容。\n\n"
        f"修改指令：{instruction}\n\n"
        f"原有内容：\n{target_section.content_md}\n\n"
        "要求：\n"
        "1. 只输出修改后的正文，不包含章节标题\n"
        "2. 禁止表格、代码块、内联代码\n"
        "3. 修改后正文："
    )

    llm = LLMService()
    try:
        new_content: str = await llm.invoke(prompt, tier="lite")
        new_content = new_content.strip()
    except Exception:
        logger.exception("doc_section_editor_llm_failed")
        return {}

    after_summary = new_content[:200]

    # Update the in-memory doc section
    updated_sections = []
    for section in doc.sections:
        if section.id == target_section.id:
            from app.schemas.artifacts import DocSection

            updated_sections.append(
                DocSection(
                    id=section.id,
                    title=section.title,
                    content_md=new_content,
                    block_ids=section.block_ids,
                )
            )
        else:
            updated_sections.append(section)

    from app.schemas.artifacts import DocArtifact

    updated_doc = DocArtifact(
        doc_id=doc.doc_id,
        title=doc.title,
        sections=updated_sections,
        share_url=doc.share_url,
    )

    # Patch the live Feishu document if we have block_ids
    if target_section.block_ids:
        try:
            from app.integrations.feishu.adapter import FeishuAdapter
            from app.services.feishu_doc_service import FeishuDocService

            adapter = FeishuAdapter()
            svc = FeishuDocService(adapter)
            await svc.patch_section(
                doc_id=doc.doc_id,
                section_block_ids=target_section.block_ids,
                section_title=target_section.title,
                new_content_md=new_content,
            )
            logger.info("doc_section_editor_patched", section=target_section.title)
        except Exception:
            logger.exception("doc_section_editor_patch_failed", section=target_section.title)

    record = ModificationRecord(
        step_index=step_index,
        scope_identifier=scope_identifier,
        instruction=instruction,
        before_summary=before_summary,
        after_summary=after_summary,
    )

    # Cap history at _MAX_HISTORY (reducer adds, so we trim proactively)
    new_history = (modification_history + [record])[-_MAX_HISTORY:]

    logger.info(
        "doc_section_editor_done",
        section=target_section.title,
        history_len=len(new_history),
    )

    doc = state.get("doc")
    share_url: str = getattr(doc, "share_url", "") or ""
    if share_url:
        pb.emit_artifact(label=f"✅ 已修改「{scope_identifier}」", url=share_url)

    return {
        "doc": updated_doc,
        "modification_history": [record],
        "mod_intent": None,
    }
