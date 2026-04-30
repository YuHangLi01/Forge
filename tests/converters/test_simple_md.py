"""Unit tests for the schema-safe simple markdown converter.

The contract is intentionally narrow: only heading1/2/3, plain text
paragraph and bullet are emitted; every element carries a single
``text_run`` with plain ``content``. These tests pin that contract so
the simple converter never accidentally grows fancy outputs that re-
introduce docx v1 schema-validation failures.
"""

from app.converters import feishu_block_types as bt
from app.converters.simple_md import md_to_simple_blocks


def _content(block: dict, key: str) -> str:
    return block[key]["elements"][0]["text_run"]["content"]


def test_h1_h2_h3() -> None:
    result = md_to_simple_blocks("# A\n## B\n### C")
    assert [b["block_type"] for b in result] == [bt.HEADING1, bt.HEADING2, bt.HEADING3]
    assert _content(result[0], "heading1") == "A"
    assert _content(result[1], "heading2") == "B"
    assert _content(result[2], "heading3") == "C"


def test_paragraph_plain() -> None:
    result = md_to_simple_blocks("Hello, Forge!")
    assert result[0]["block_type"] == bt.TEXT
    assert _content(result[0], "text") == "Hello, Forge!"


def test_bullets_dash_and_star() -> None:
    result = md_to_simple_blocks("- one\n* two")
    assert all(b["block_type"] == bt.BULLET for b in result)
    assert _content(result[0], "bullet") == "one"
    assert _content(result[1], "bullet") == "two"


def test_inline_markers_stripped_from_paragraph() -> None:
    """Bold/italic/inline code don't go through; they're stripped to plain text."""
    result = md_to_simple_blocks("**bold** and `code` and *italic*")
    text = _content(result[0], "text")
    assert "bold" in text and "code" in text and "italic" in text
    # No markdown markers remain
    assert "**" not in text and "`" not in text


def test_blank_lines_skipped() -> None:
    result = md_to_simple_blocks("# A\n\n\nbody\n\n- bullet\n")
    assert len(result) == 3


def test_ordered_list_renders_as_bullet() -> None:
    """Ordered lists also degrade to bullet for safety."""
    result = md_to_simple_blocks("1. first\n2. second")
    assert all(b["block_type"] == bt.BULLET for b in result)
    assert _content(result[0], "bullet") == "first"


def test_code_fence_emits_text_lines() -> None:
    result = md_to_simple_blocks("before\n```python\nx = 1\ny = 2\n```\nafter")
    types = [b["block_type"] for b in result]
    # before, x=1, y=2, after — all TEXT (no CODE block in the safe converter)
    assert all(t == bt.TEXT for t in types)


def test_table_degrades_to_text() -> None:
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    result = md_to_simple_blocks(md)
    assert all(b["block_type"] == bt.TEXT for b in result)


def test_every_block_uses_text_run_oneof() -> None:
    """Schema invariant: each element is exactly {'text_run': {...}}."""
    md = "# Title\n\nbody.\n\n- a\n- b"
    for block in md_to_simple_blocks(md):
        kind_key = next(k for k in block if k != "block_type")
        elements = block[kind_key]["elements"]
        for el in elements:
            assert set(el.keys()) == {"text_run"}
            assert "content" in el["text_run"]
            # No flat 'tag'/'content' shape
            assert "tag" not in el


def test_empty_markdown() -> None:
    assert md_to_simple_blocks("") == []
    assert md_to_simple_blocks("   \n   \n") == []
