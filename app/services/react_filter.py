"""ReAct filter: strip internal thinking blocks and sanitize user-visible text."""

from __future__ import annotations

import re
from collections.abc import Callable

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Sentences matching these opening phrases are removed entirely.
_FILLER_STARTERS: tuple[str, ...] = ("作为", "根据", "我理解")

# Sentences containing these English technical terms (whole-word) are removed.
_TECH_WORD_RE = re.compile(r"\b(intent|token|ambiguity|score|LLM|prompt)\b", re.IGNORECASE)

# Inline phrase replacements applied after sentence-level filtering.
_BANNED_PHRASES: list[tuple[str, str]] = [
    ("用户的输入很奇怪", "正在分析中..."),
    ("这个用户", "正在分析中..."),
    ("用户似乎", "正在分析中..."),
    ("用户的", "正在分析中..."),
    ("奇怪", "正在分析中..."),
    ("不合理", "正在分析中..."),
    ("我需要谨慎", "正在处理..."),
    ("我无法确定", "正在处理..."),
    ("作为AI", ""),
    ("作为人工智能", ""),
]

_MAX_LEN = 60
_SENTENCE_SPLIT_RE = re.compile(r"([。！？\n]+)")


def strip_thinking(text: str) -> str:
    """Remove <thinking>…</thinking> and <think>…</think> blocks from *text*."""
    text = _THINKING_TAG_RE.sub("", text)
    text = _THINK_TAG_RE.sub("", text)
    return text.strip()


def _extract_thinking(text: str) -> str:
    """Return the raw content of the first <thinking> block, or empty string."""
    m = _THINKING_TAG_RE.search(text) or _THINK_TAG_RE.search(text)
    if not m:
        return ""
    inner = re.sub(r"</?think(?:ing)?>", "", m.group(), flags=re.IGNORECASE)
    return inner.strip()


def _filter_sentences(text: str, pred: Callable[[str], bool]) -> str:
    """Remove sentences (split on 。！？\\n) that match *pred*."""
    parts = _SENTENCE_SPLIT_RE.split(text)
    out: list[str] = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        delimiter = parts[i + 1] if i + 1 < len(parts) else ""
        if chunk.strip() and pred(chunk):
            i += 2
            continue
        out.append(chunk)
        if delimiter:
            out.append(delimiter)
        i += 2
    return "".join(out).strip()


def sanitize(text: str) -> str:
    """Full sanitization pipeline for user-visible progress text.

    Order: strip thinking → remove filler sentences → remove tech-word sentences
           → blacklist phrase replacement → truncate to 60 chars.
    """
    # 1. Strip <thinking> blocks
    text = strip_thinking(text)

    # 2. Remove sentences that start with filler openers
    text = _filter_sentences(text, lambda s: any(s.strip().startswith(p) for p in _FILLER_STARTERS))

    # 3. Remove sentences that contain technical terms
    text = _filter_sentences(text, lambda s: bool(_TECH_WORD_RE.search(s)))

    # 4. Blacklist phrase replacement
    for phrase, replacement in _BANNED_PHRASES:
        if phrase in text:
            text = text.replace(phrase, replacement)

    text = text.strip()

    # 5. Truncate
    if len(text) > _MAX_LEN:
        text = text[:_MAX_LEN] + "…"

    return text
