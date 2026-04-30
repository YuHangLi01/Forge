"""ReAct filter: strip internal thinking blocks and sanitize user-visible text."""

from __future__ import annotations

import re

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_BANNED_PHRASES: list[tuple[str, str]] = [
    ("用户的输入很奇怪", "正在分析中..."),
    ("这个用户", "正在分析中..."),
    ("用户似乎", "正在分析中..."),
    ("我需要谨慎", "正在处理..."),
    ("我无法确定", "正在处理..."),
    ("作为AI", ""),
    ("作为人工智能", ""),
]


def strip_thinking(text: str) -> str:
    """Remove <thinking>…</thinking> and <think>…</think> blocks from *text*."""
    text = _THINKING_TAG_RE.sub("", text)
    text = _THINK_TAG_RE.sub("", text)
    return text.strip()


def sanitize(text: str) -> str:
    """Strip thinking blocks then replace any blacklisted phrases."""
    text = strip_thinking(text)
    for phrase, replacement in _BANNED_PHRASES:
        if phrase in text:
            text = text.replace(phrase, replacement)
    return text.strip()
