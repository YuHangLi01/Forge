from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_CLARIFY_RESUME_NODE = "clarify_resume"


def graph_node(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for all LangGraph work nodes.

    Provides two cross-cutting concerns:
    1. Race protection: if ``pending_user_action`` is set and the current node
       is not ``clarify_resume``, returns ``{}`` immediately (no-op state
       update) so the graph stays paused while waiting for human input.
    2. Structured logging on enter/exit for each node invocation.

    LangSmith span injection (with raw_input redaction) is added in T07 when
    the prompt versioning + tracing infrastructure is in place.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            if state.get("pending_user_action") and name != _CLARIFY_RESUME_NODE:
                logger.debug("graph_node_skipped_pending_action", node=name)
                return {}

            logger.debug("graph_node_enter", node=name)
            result: dict[str, Any] = await fn(state)
            logger.debug("graph_node_exit", node=name)
            return result

        wrapper.__node_name__ = name  # type: ignore[attr-defined]
        return wrapper

    return decorator
