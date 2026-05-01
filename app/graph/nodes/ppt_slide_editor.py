"""ppt_slide_editor node stub — full implementation in S3-T05."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node

logger = structlog.get_logger(__name__)


@graph_node("ppt_slide_editor")
async def ppt_slide_editor_node(state: dict[str, Any]) -> dict[str, Any]:
    logger.warning("ppt_slide_editor_stub", msg="S3-T05 not yet implemented")
    return {"error": "PPT 幻灯片编辑功能暂未开放，敬请期待"}
