from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_CLARIFY_RESUME_NODE = "clarify_resume"

# Nodes that should not pause even when pending_user_action is set.
_PAUSE_EXEMPT_NODES: frozenset[str] = frozenset({_CLARIFY_RESUME_NODE, "checkpoint_control"})


def _write_langsmith_span(node_name: str, duration_ms: float, metadata: dict[str, Any]) -> None:
    """Write node metadata to the active LangSmith run span, if tracing is enabled."""
    try:
        from langsmith.run_helpers import get_current_run_tree

        run = get_current_run_tree()
        if run is None:
            return
        run.add_metadata(
            {
                "forge_node": node_name,
                "duration_ms": round(duration_ms, 1),
                **metadata,
            }
        )
    except Exception:
        pass  # LangSmith unavailable or not configured — silent no-op


def graph_node(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for all LangGraph work nodes.

    Cross-cutting concerns:
    1. Race protection: if ``pending_user_action`` is set and this node is not
       in ``_PAUSE_EXEMPT_NODES``, returns ``{}`` immediately so the graph stays
       paused while waiting for human input.
    2. Structured logging on enter/exit with wall-clock duration.
    3. LangSmith span metadata: node name, duration, and any ``_trace_*`` keys
       set in the node's return dict (stripped before state update).
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            if state.get("pending_user_action") and name not in _PAUSE_EXEMPT_NODES:
                logger.debug("graph_node_skipped_pending_action", node=name)
                return {}

            logger.debug("graph_node_enter", node=name)
            t0 = time.monotonic()
            result: dict[str, Any] = await fn(state)
            duration_ms = (time.monotonic() - t0) * 1000
            logger.debug("graph_node_exit", node=name, duration_ms=round(duration_ms, 1))

            # Extract optional trace metadata set by the node (kept out of state).
            span_meta: dict[str, Any] = {}
            trace_keys = [k for k in result if k.startswith("_trace_")]
            for k in trace_keys:
                span_meta[k[len("_trace_") :]] = result.pop(k)

            _write_langsmith_span(name, duration_ms, span_meta)
            return result

        wrapper.__node_name__ = name  # type: ignore[attr-defined]
        return wrapper

    return decorator
