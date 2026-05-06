"""Utilities for formatting retrieved ChromaDB context into LLM prompt strings."""

from __future__ import annotations

from typing import Any


def format_retrieved_context(
    ctx: list[dict[str, Any]], max_items: int = 5, max_chars: int = 400
) -> str:
    """Format a list of retrieved context chunks into a readable prompt string.

    Each entry is labelled with its source and timestamp (if available) so the
    LLM can distinguish personal notes from delivered artifacts.

    Args:
        ctx: list of dicts with 'text' and optional 'metadata' keys (ChromaDB result format).
        max_items: maximum number of chunks to include.
        max_chars: maximum characters per chunk's text.

    Returns:
        Multi-line string ready for {context_summary} substitution in prompts,
        or "（无背景资料）" when ctx is empty.
    """
    if not ctx:
        return "（无背景资料）"

    lines: list[str] = []
    for i, c in enumerate(ctx[:max_items], 1):
        meta: dict[str, Any] = c.get("metadata") or {}
        source_label = meta.get("source", "delivered")
        ts = meta.get("ts", "")
        label = f"{source_label} {ts}".strip() if ts else source_label
        text = c.get("text", "")[:max_chars]
        lines.append(f"[{i}] {label}: {text}")
    return "\n".join(lines)
