from __future__ import annotations

from typing import Any

_registry: dict[str, Any] = {}


def register(name: str, instance: Any) -> None:
    """Register a named tool/service instance (LLM, Chroma, FeishuDoc, etc.)."""
    _registry[name] = instance


def get(name: str) -> Any:
    """Retrieve a registered instance by name.  Raises KeyError if not found."""
    if name not in _registry:
        raise KeyError(f"Tool '{name}' not registered. Call register() first.")
    return _registry[name]


def clear() -> None:
    """Remove all registrations.  Intended for test teardown only."""
    _registry.clear()
