"""Prompt version registry.

Usage:
    from app.prompts._versioning import PromptVersion, register, get

    V1 = PromptVersion(version="v1", node="intent_parser", text="...")
    register(V1)
    prompt = get("intent_parser")           # returns CURRENT
    prompt = get("intent_parser", "v1")     # returns v1 explicitly
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# node_name → version_tag → PromptVersion
_registry: dict[str, dict[str, PromptVersion]] = {}
_CURRENT_TAG = "CURRENT"


class PromptVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    node: str
    text: str


def register(prompt: PromptVersion, *, make_current: bool = True) -> None:
    """Register a prompt version.  If make_current=True (default), also set it as CURRENT."""
    node_registry = _registry.setdefault(prompt.node, {})
    node_registry[prompt.version] = prompt
    if make_current:
        node_registry[_CURRENT_TAG] = prompt


def get(node: str, version: str = _CURRENT_TAG) -> PromptVersion:
    """Retrieve a registered prompt by node + version tag.

    Raises KeyError if the node or version has not been registered.
    """
    if node not in _registry:
        raise KeyError(f"No prompts registered for node '{node}'")
    node_registry = _registry[node]
    if version not in node_registry:
        raise KeyError(f"Prompt version '{version}' not found for node '{node}'")
    return node_registry[version]


def clear() -> None:
    """Remove all registrations.  Test teardown use only."""
    _registry.clear()
