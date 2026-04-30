"""Minimal, schema-safe Markdown → Feishu Block converter.

Only emits the three block types we have high confidence Feishu's docx v1
``create_document_block_children`` accepts:

- heading1 / heading2 / heading3 (block_type 3 / 4 / 5)
- text paragraph (block_type 2)
- bullet list item (block_type 12)

Inline content is always a single ``text_run`` with plain ``content``;
no bold/italic/inline_code/links/etc. Tables, code fences, ordered lists,
images and quotes degrade to plain text or are dropped.

This converter exists alongside ``md_to_feishu_blocks`` (the richer
parser) for situations where reliability matters more than fidelity —
notably the Stage 1 demo pipeline. The richer converter can be revived
once we've finished mapping all docx v1 schema quirks (see PR history of
fix/feishu-block-schema-fields).
"""

from typing import Any

from app.converters import feishu_block_types as bt


def md_to_simple_blocks(markdown: str) -> list[dict[str, Any]]:
    """Render markdown as a flat list of safe Feishu Block dicts."""
    blocks: list[dict[str, Any]] = []
    in_code_fence = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            blocks.append(_text(line))
            continue
        if not line.strip():
            # blank line — visually a separator; no block needed
            continue

        # Headings
        if line.startswith("### "):
            blocks.append(_heading(3, line[4:].strip()))
        elif line.startswith("## "):
            blocks.append(_heading(2, line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(_heading(1, line[2:].strip()))
        # Bullets: '- item' or '* item'
        elif line.lstrip().startswith(("- ", "* ")):
            stripped = line.lstrip()
            content = stripped[2:].strip()
            blocks.append(_bullet(content))
        # Ordered list: '1. item' / '12. item'
        elif _is_ordered_line(line):
            content = _strip_ordered_prefix(line)
            blocks.append(_bullet(content))  # render as bullet to keep it safe
        # Tables and other fancy stuff — fall through as plain text
        else:
            content = _strip_inline_markers(line)
            blocks.append(_text(content))

    return blocks


def _heading(level: int, content: str) -> dict[str, Any]:
    block_type = bt.HEADING_LEVEL_MAP.get(level, bt.HEADING1)
    key = {bt.HEADING1: "heading1", bt.HEADING2: "heading2", bt.HEADING3: "heading3"}.get(
        block_type, "heading1"
    )
    return {
        "block_type": block_type,
        key: {"elements": [{"text_run": {"content": content}}], "style": {}},
    }


def _text(content: str) -> dict[str, Any]:
    return {
        "block_type": bt.TEXT,
        "text": {"elements": [{"text_run": {"content": content}}], "style": {}},
    }


def _bullet(content: str) -> dict[str, Any]:
    return {
        "block_type": bt.BULLET,
        "bullet": {"elements": [{"text_run": {"content": content}}], "style": {}},
    }


def _is_ordered_line(line: str) -> bool:
    stripped = line.lstrip()
    head, sep, _ = stripped.partition(". ")
    return bool(sep) and head.isdigit()


def _strip_ordered_prefix(line: str) -> str:
    stripped = line.lstrip()
    _, _, rest = stripped.partition(". ")
    return rest.strip()


def _strip_inline_markers(line: str) -> str:
    """Strip the most common markdown inline markers without parsing them."""
    out = line
    for marker in ("**", "__", "*", "_", "`"):
        out = out.replace(marker, "")
    # Pipe-table row: leave the pipes — they're already plain text
    return out
