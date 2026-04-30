"""Light-weight intent classifier for Stage 1.

Stage 1 needs only two intents:
- ``generate_demo`` — produce a sample meeting Doc + PPT and reply with links.
- ``chat`` — fallback Echo path through Doubao.

Keyword matching is intentional, not LLM-based:
- Predictable for the demo (no flaky model calls).
- Cheaper (no LLM round-trip on every message).
- Easy to extend in Stage 2 by replacing this module with an LLM router.
"""

from typing import Literal

Intent = Literal["chat", "generate_demo"]

_DEMO_TRIGGERS: tuple[str, ...] = (
    "生成ppt",
    "生成 ppt",
    "生成幻灯片",
    "生成文档",
    "生成 doc",
    "生成会议纪要",
    "生成纪要",
    "demo",
    "示例文档",
)


def classify(text: str) -> Intent:
    """Return the intent label for a piece of user text."""
    if not text:
        return "chat"
    needle = text.strip().lower()
    for trigger in _DEMO_TRIGGERS:
        if trigger in needle:
            return "generate_demo"
    return "chat"
