"""feishu_doc_write node: write generated markdown to Feishu (simple=True, D-3)."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus

logger = structlog.get_logger(__name__)


@graph_node("feishu_doc_write")
async def feishu_doc_write_node(state: dict[str, Any]) -> dict[str, Any]:
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.feishu_doc_service import FeishuDocService

    doc_markdown: str = state.get("doc_markdown", "")
    in_mem_doc = state.get("doc")
    title: str = getattr(in_mem_doc, "title", "文档") if in_mem_doc else "文档"

    if not doc_markdown.strip():
        logger.warning("feishu_doc_write_empty_markdown")
        return {}

    adapter = FeishuAdapter()
    svc = FeishuDocService(adapter)

    doc = await svc.create_from_markdown(title=title, markdown=doc_markdown, simple=True)

    # Grant public read access (tenant_readable) so the share URL works
    try:
        await adapter.set_permission_public(doc.doc_id, type_="docx")
    except Exception:
        logger.exception("feishu_doc_write_permission_failed", doc_id=doc.doc_id)

    logger.info(
        "feishu_doc_write_done",
        doc_id=doc.doc_id,
        share_url=doc.share_url,
        n_sections=len(doc.sections),
    )
    return {"doc": doc, "status": TaskStatus.completed}
