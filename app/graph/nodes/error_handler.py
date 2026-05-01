"""error_handler node: emit error/cancel card and terminate the graph."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)


@graph_node("error_handler")
async def error_handler_node(state: dict[str, Any]) -> dict[str, Any]:
    message_id: str = state.get("message_id", "")
    error: str = state.get("error", "") or ""
    from app.schemas.enums import TaskStatus

    status = state.get("status")
    if status == TaskStatus.cancelled:
        display_msg = error or "任务已取消"
    else:
        display_msg = error or "处理过程中出现错误，请稍后重试"

    logger.info("error_handler_invoked", message_id=message_id, error=error, status=status)

    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.emit_error(display_msg)

    return {}
