from __future__ import annotations

from typing import Any

from app.graph.builder import build_graph

_graph: Any = None


def get_graph(checkpointer: Any = None) -> Any:
    """Return the module-level graph singleton.

    Production startup calls ``get_graph(checkpointer=await create_checkpointer())``
    once.  Subsequent calls with no argument return the cached instance.
    Tests call ``build_graph(None)`` directly to get a fresh graph without
    polluting the singleton.
    """
    global _graph
    if _graph is None:
        _graph = build_graph(checkpointer)
    return _graph


def reset_graph() -> None:
    """Reset the singleton.  Test teardown use only."""
    global _graph
    _graph = None


__all__ = ["build_graph", "get_graph", "reset_graph"]
