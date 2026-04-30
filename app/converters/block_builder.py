"""Build Feishu Block JSON from parsed markdown tokens."""

from typing import Any

from app.converters import feishu_block_types as bt


def heading_block(level: int, elements: list[dict[str, Any]]) -> dict[str, Any]:
    block_type = bt.HEADING_LEVEL_MAP.get(level, bt.HEADING1)
    key = {bt.HEADING1: "heading1", bt.HEADING2: "heading2", bt.HEADING3: "heading3"}.get(
        block_type, "heading1"
    )
    # docx v1 TextStyle expects an empty dict (no extra fields needed).
    return {
        "block_type": block_type,
        key: {"elements": elements, "style": {}},
    }


def text_block(elements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "block_type": bt.TEXT,
        "text": {"elements": elements, "style": {}},
    }


def bullet_block(elements: list[dict[str, Any]], indent: int = 0) -> dict[str, Any]:
    # docx v1 doesn't expose a numeric indent on TextStyle; the field is
    # 'indentation_level' (string) and only "1" is documented as supported,
    # so we leave style empty and rely on Feishu's default rendering for
    # nested lists. Indent depth is preserved by the caller chunking blocks.
    _ = indent  # kept for future use; no field accepts numeric indent
    return {
        "block_type": bt.BULLET,
        "bullet": {"elements": elements, "style": {}},
    }


def ordered_block(elements: list[dict[str, Any]], indent: int = 0) -> dict[str, Any]:
    _ = indent
    return {
        "block_type": bt.ORDERED,
        "ordered": {"elements": elements, "style": {}},
    }


def code_block(language: str, code_text: str) -> dict[str, Any]:
    lang = bt.CODE_LANG_MAP.get(language.lower(), bt.CODE_LANG_PLAIN)
    return {
        "block_type": bt.CODE,
        "code": {
            "elements": [{"text_run": {"content": code_text}}],
            "style": {"language": lang, "wrap": False},
        },
    }


def _plain_run(content: str) -> dict[str, Any]:
    return {"text_run": {"content": content}}


def table_block(rows: list[list[str]]) -> dict[str, Any]:
    """Render a markdown table.

    Note: Feishu's docx v1 TableBlock expects ``cells`` as a list of
    block_ids (strings) referring to pre-created TableCell child blocks,
    not inline block payloads. Building that two-phase structure inside
    one ``create_document_block_children`` call isn't supported, so for
    now we degrade tables to a sequence of text blocks: one row per line,
    cells separated by ' | '. Visually less rich, but valid and reliable.
    """
    if not rows:
        return text_block([_plain_run("(empty table)")])
    body = "\n".join(" | ".join(row) for row in rows)
    return text_block([_plain_run(body)])
