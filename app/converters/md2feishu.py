"""Convert Markdown to Feishu Doc API block request list."""

from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.converters.block_builder import (
    bullet_block,
    code_block,
    heading_block,
    ordered_block,
    table_block,
    text_block,
)
from app.converters.inline_parser import parse_inline_tokens

_md = MarkdownIt().enable("table").enable("strikethrough")


def md_to_feishu_blocks(
    markdown: str,
    parent_block_id: str = "root",  # noqa: ARG001 — kept for back-compat
) -> list[dict[str, Any]]:
    """Convert Markdown string to a list of Feishu Block dicts.

    Each entry is a raw Block payload (``{"block_type": ..., "<kind>": {...}}``)
    suitable for the docx v1 ``create_document_block_children`` API as the
    ``children`` array. ``parent_block_id`` is unused at this layer — the
    adapter passes the actual parent (the document_id by default) when
    invoking the API.
    """
    tokens = _md.parse(markdown)
    return _parse_token_stream(tokens)


def _parse_token_stream(tokens: list[Token]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1])  # h1 → 1, h2 → 2, ...
            inline_tok = tokens[i + 1] if i + 1 < len(tokens) else None
            elements = parse_inline_tokens(inline_tok.children or []) if inline_tok else []
            blocks.append(heading_block(level, elements))
            i += 3  # heading_open, inline, heading_close

        elif tok.type == "paragraph_open":
            inline_tok = tokens[i + 1] if i + 1 < len(tokens) else None
            elements = parse_inline_tokens(inline_tok.children or []) if inline_tok else []
            blocks.append(text_block(elements))
            i += 3

        elif tok.type == "bullet_list_open":
            list_blocks, consumed = _parse_list(tokens, i, ordered=False, indent=0)
            blocks.extend(list_blocks)
            i += consumed

        elif tok.type == "ordered_list_open":
            list_blocks, consumed = _parse_list(tokens, i, ordered=True, indent=0)
            blocks.extend(list_blocks)
            i += consumed

        elif tok.type == "fence":
            lang = tok.info.strip() if tok.info else ""
            blocks.append(code_block(lang, tok.content.rstrip("\n")))
            i += 1

        elif tok.type == "table_open":
            table, consumed = _parse_table(tokens, i)
            blocks.append(table)
            i += consumed

        elif tok.type in ("html_block", "hr"):
            # Degrade HTML blocks and horizontal rules to plain text
            content = tok.content.strip()
            elements = [{"text_run": {"content": content}}] if content else []
            blocks.append(text_block(elements))
            i += 1

        else:
            i += 1

    return blocks


def _parse_list(
    tokens: list[Token], start: int, ordered: bool, indent: int
) -> tuple[list[dict[str, Any]], int]:
    """Parse a bullet or ordered list, return (blocks, tokens_consumed)."""
    blocks: list[dict[str, Any]] = []
    open_tag = "ordered_list_open" if ordered else "bullet_list_open"
    close_tag = "ordered_list_close" if ordered else "bullet_list_close"
    depth = 0
    i = start

    while i < len(tokens):
        tok = tokens[i]

        if tok.type == open_tag:
            depth += 1
            i += 1

        elif tok.type == close_tag:
            depth -= 1
            i += 1
            if depth == 0:
                break

        elif tok.type == "list_item_open":
            i += 1
            # Collect inline content for this list item
            if i < len(tokens) and tokens[i].type == "paragraph_open":
                inline_tok = tokens[i + 1] if i + 1 < len(tokens) else None
                elements = parse_inline_tokens(inline_tok.children or []) if inline_tok else []
                i += 3  # paragraph_open, inline, paragraph_close
            else:
                elements = []

            if ordered:
                blocks.append(ordered_block(elements, indent=min(indent, 2)))
            else:
                blocks.append(bullet_block(elements, indent=min(indent, 2)))

            # Handle nested lists
            while i < len(tokens) and tokens[i].type in (
                "bullet_list_open",
                "ordered_list_close",
                "ordered_list_open",
            ):
                if tokens[i].type in ("bullet_list_open", "ordered_list_open"):
                    nested_ordered = tokens[i].type == "ordered_list_open"
                    nested, consumed = _parse_list(tokens, i, nested_ordered, indent + 1)
                    blocks.extend(nested)
                    i += consumed
                else:
                    break

        elif tok.type == "list_item_close":
            i += 1
        else:
            i += 1

    return blocks, i - start


def _parse_table(tokens: list[Token], start: int) -> tuple[dict[str, Any], int]:
    """Parse a table token block, return (table_block, tokens_consumed)."""
    rows: list[list[str]] = []
    current_row: list[str] = []
    in_cell = False
    i = start

    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "table_close":
            i += 1
            break
        elif tok.type == "tr_open":
            current_row = []
        elif tok.type == "tr_close":
            if current_row:
                rows.append(current_row)
        elif tok.type in ("th_open", "td_open"):
            in_cell = True
        elif tok.type in ("th_close", "td_close"):
            in_cell = False
        elif tok.type == "inline" and in_cell:
            current_row.append(tok.content.strip())
        i += 1

    return table_block(rows), i - start
