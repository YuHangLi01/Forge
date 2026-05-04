"""error_handler node: classify error, emit appropriate card, and terminate the graph."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

# Degradation matrix: maps error substring patterns to (user_message, log_level)
_DEGRADATION_MATRIX: list[tuple[str, str, str]] = [
    # (error_pattern, user_facing_message, log_level)
    ("429", "LLM 请求超出速率限制，请稍后重试", "warning"),
    ("RateLimitExceeded", "LLM 请求超出速率限制，请稍后重试", "warning"),
    ("timeout", "请求超时，请稍后重试", "warning"),
    ("Timeout", "请求超时，请稍后重试", "warning"),
    ("500", "飞书服务暂时不可用，请稍后重试", "error"),
    ("ServiceUnavailable", "飞书服务暂时不可用，请稍后重试", "error"),
    ("ConnectionError", "网络连接错误，请检查服务状态", "error"),
]

_DEFAULT_ERROR_MSG = "处理过程中出现错误，请稍后重试"


def _classify_error(error: str) -> tuple[str, str]:
    """Return (user_message, log_level) based on error string content."""
    for pattern, user_msg, level in _DEGRADATION_MATRIX:
        if pattern in error:
            return user_msg, level
    return _DEFAULT_ERROR_MSG, "error"


@graph_node("error_handler")
async def error_handler_node(state: dict[str, Any]) -> dict[str, Any]:
    message_id: str = state.get("message_id", "")
    error: str = state.get("error", "") or ""
    from app.schemas.enums import TaskStatus

    status = state.get("status")
    if status == TaskStatus.cancelled:
        display_msg = error or "任务已取消"
        log_level = "info"
    else:
        display_msg, log_level = _classify_error(error)
        if not error:
            display_msg = _DEFAULT_ERROR_MSG

    if log_level == "warning":
        log_fn = logger.warning
    elif log_level == "info":
        log_fn = logger.info
    else:
        log_fn = logger.error
    log_fn(
        "error_handler_invoked",
        message_id=message_id,
        error=error,
        status=status,
        display_msg=display_msg,
    )

    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.emit_error(display_msg)

    # Set status=completed so a stale checkpoint doesn't re-trigger error_handler
    # on the next graph resume (task_continue / checkpoint_resume).
    return {"status": TaskStatus.completed}
