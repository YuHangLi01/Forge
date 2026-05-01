"""feishu_ppt_write node stub — full implementation in S3-T04."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node

logger = structlog.get_logger(__name__)


@graph_node("feishu_ppt_write")
async def feishu_ppt_write_node(state: dict[str, Any]) -> dict[str, Any]:
    logger.warning("feishu_ppt_write_stub", msg="S3-T04 not yet implemented")
    return {"error": "PPT 上传功能暂未开放，敬请期待"}
