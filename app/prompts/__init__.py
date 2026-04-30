"""Prompt registry public API.

Usage:
    from app.prompts import register_prompt, get_prompt

    register_prompt(my_prompt_version)
    prompt = get_prompt("intent_parser")         # CURRENT
    prompt = get_prompt("intent_parser", "v1")   # explicit version
"""

from app.prompts._versioning import PromptVersion, clear, get, register

__all__ = ["PromptVersion", "clear", "get", "register"]


def register_prompt(prompt: PromptVersion, *, make_current: bool = True) -> None:
    register(prompt, make_current=make_current)


def get_prompt(node: str, version: str = "CURRENT") -> PromptVersion:
    return get(node, version)
