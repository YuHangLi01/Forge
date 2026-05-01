from __future__ import annotations

from typing import Any

from app.graph.builder import build_graph

_graph: Any = None


def get_graph(checkpointer: Any = None) -> Any:
    """Return the module-level graph singleton.

    Prefer ``get_or_init_graph()`` in async contexts so the PostgreSQL
    checkpointer is automatically created when first needed.
    Tests call ``build_graph(None)`` directly to get a fresh graph without
    polluting the singleton.
    """
    global _graph
    if _graph is None:
        _graph = build_graph(checkpointer)
    return _graph


async def get_or_init_graph() -> Any:
    """Return the singleton, lazily creating an AsyncPostgresSaver if needed.

    Safe to call from any async context (FastAPI lifespan, Celery async tasks).
    The pool and checkpointer are created once and reused for the process lifetime.
    """
    global _graph
    if _graph is not None:
        return _graph
    from app.db.checkpointer import create_checkpointer

    checkpointer = await create_checkpointer()
    _graph = build_graph(checkpointer)
    return _graph


def reset_graph() -> None:
    """Reset the singleton.  Test teardown use only."""
    global _graph
    _graph = None


__all__ = ["build_graph", "get_graph", "get_or_init_graph", "reset_graph"]
