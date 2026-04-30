"""Build Feishu Block JSON from parsed markdown tokens."""

from typing import Any

from app.converters import feishu_block_types as bt


def heading_block(level: int, elements: list[dict[str, Any]]) -> dict[str, Any]:
    block_type = bt.HEADING_LEVEL_MAP.get(level, bt.HEADING1)
    key = {bt.HEADING1: "heading1", bt.HEADING2: "heading2", bt.HEADING3: "heading3"}.get(
        block_type, "heading1"
    )
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
    return {
        "block_type": bt.BULLET,
        "bullet": {"elements": elements, "style": {"indent_level": indent}},
    }


def ordered_block(elements: list[dict[str, Any]], indent: int = 0) -> dict[str, Any]:
    return {
        "block_type": bt.ORDERED,
        "ordered": {"elements": elements, "style": {"indent_level": indent}},
    }


def code_block(language: str, code_text: str) -> dict[str, Any]:
    lang = bt.CODE_LANG_MAP.get(language.lower(), "PlainText")
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
    if not rows:
        return text_block([_plain_run("(empty table)")])
    col_count = max(len(r) for r in rows)
    row_count = len(rows)
    cells = []
    for row in rows:
        for cell_text in row:
            cells.append(
                {
                    "block_type": bt.TEXT,
                    "text": {"elements": [_plain_run(cell_text)], "style": {}},
                }
            )
        for _ in range(col_count - len(row)):
            cells.append(
                {
                    "block_type": bt.TEXT,
                    "text": {"elements": [_plain_run("")], "style": {}},
                }
            )
    return {
        "block_type": bt.TABLE,
        "table": {
            "cells": cells,
            "property": {
                "row_size": row_count,
                "column_size": col_count,
                "column_width": [120] * col_count,
                "merge_info": [],
                "header_row": True,
                "header_column": False,
            },
        },
    }
