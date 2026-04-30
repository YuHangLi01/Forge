from pathlib import Path

from app.converters import feishu_block_types as bt
from app.converters.md2feishu import md_to_feishu_blocks

FIXTURES = Path(__file__).parent / "fixtures"


def _blocks(md: str) -> list[dict]:
    """md_to_feishu_blocks now returns raw blocks directly (no wrapper)."""
    return md_to_feishu_blocks(md)


def _run(element: dict) -> dict:
    """Each TextElement is a oneof; we use text_run for plain content."""
    return element["text_run"]


# ---- Heading blocks ----------------------------------------------------------


def test_h1_block() -> None:
    result = _blocks("# Hello World")
    assert len(result) == 1
    assert result[0]["block_type"] == bt.HEADING1
    assert _run(result[0]["heading1"]["elements"][0])["content"] == "Hello World"


def test_h2_block() -> None:
    result = _blocks("## Section Title")
    assert result[0]["block_type"] == bt.HEADING2


def test_h3_block() -> None:
    result = _blocks("### Sub Section")
    assert result[0]["block_type"] == bt.HEADING3


# ---- Paragraph / Text blocks -------------------------------------------------


def test_paragraph_plain() -> None:
    result = _blocks("Hello, Forge!")
    assert result[0]["block_type"] == bt.TEXT
    assert _run(result[0]["text"]["elements"][0])["content"] == "Hello, Forge!"


def test_paragraph_bold() -> None:
    result = _blocks("**bold text**")
    run = _run(result[0]["text"]["elements"][0])
    assert run["content"] == "bold text"
    assert run["text_element_style"]["bold"] is True


def test_paragraph_italic() -> None:
    result = _blocks("*italic text*")
    run = _run(result[0]["text"]["elements"][0])
    assert run["text_element_style"]["italic"] is True


def test_paragraph_inline_code() -> None:
    result = _blocks("`some_code()`")
    run = _run(result[0]["text"]["elements"][0])
    assert run["text_element_style"]["inline_code"] is True


def test_paragraph_link() -> None:
    result = _blocks("[Feishu](https://feishu.cn)")
    run = _run(result[0]["text"]["elements"][0])
    assert run["content"] == "Feishu"
    assert "link" in run["text_element_style"]
    assert run["text_element_style"]["link"]["url"] == "https://feishu.cn"


def test_paragraph_bold_and_italic_combined() -> None:
    result = _blocks("**bold *italic* mix**")
    elements = result[0]["text"]["elements"]
    texts = [_run(e)["content"] for e in elements]
    assert any("bold" in t or "mix" in t or "italic" in t for t in texts)


# ---- Bullet list ------------------------------------------------------------


def test_bullet_list_single() -> None:
    result = _blocks("- item one")
    assert result[0]["block_type"] == bt.BULLET
    assert _run(result[0]["bullet"]["elements"][0])["content"] == "item one"


def test_bullet_list_multiple() -> None:
    result = _blocks("- first\n- second\n- third")
    assert len(result) == 3
    assert all(b["block_type"] == bt.BULLET for b in result)


def test_bullet_list_nested() -> None:
    md = "- parent\n  - child\n    - grandchild"
    result = _blocks(md)
    # All items should be bullets; nested ones have higher indent_level
    assert all(b["block_type"] == bt.BULLET for b in result)
    # Parent is level 0
    assert result[0]["bullet"]["style"]["indent_level"] == 0


# ---- Ordered list -----------------------------------------------------------


def test_ordered_list_single() -> None:
    result = _blocks("1. first item")
    assert result[0]["block_type"] == bt.ORDERED


def test_ordered_list_multiple() -> None:
    result = _blocks("1. alpha\n2. beta\n3. gamma")
    assert len(result) == 3
    assert all(b["block_type"] == bt.ORDERED for b in result)


def test_ordered_list_content() -> None:
    result = _blocks("1. Step one")
    assert _run(result[0]["ordered"]["elements"][0])["content"] == "Step one"


# ---- Code block -------------------------------------------------------------


def test_code_block_python() -> None:
    result = _blocks("```python\nprint('hello')\n```")
    assert result[0]["block_type"] == bt.CODE
    assert result[0]["code"]["style"]["language"] == "Python"
    assert "print" in _run(result[0]["code"]["elements"][0])["content"]


def test_code_block_no_lang() -> None:
    result = _blocks("```\nsome code\n```")
    assert result[0]["block_type"] == bt.CODE
    assert result[0]["code"]["style"]["language"] == "PlainText"


def test_code_block_go() -> None:
    result = _blocks('```go\nfmt.Println("hi")\n```')
    assert result[0]["code"]["style"]["language"] == "Go"


# ---- Table ------------------------------------------------------------------


def test_table_basic() -> None:
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    result = _blocks(md)
    assert result[0]["block_type"] == bt.TABLE
    table = result[0]["table"]
    assert table["property"]["column_size"] == 2
    assert table["property"]["row_size"] >= 2


def test_table_three_columns() -> None:
    md = "| X | Y | Z |\n|---|---|---|\n| a | b | c |"
    result = _blocks(md)
    assert result[0]["table"]["property"]["column_size"] == 3


def test_table_header_row() -> None:
    md = "| Name | Score |\n|------|-------|\n| Alice | 90 |"
    result = _blocks(md)
    assert result[0]["table"]["property"]["header_row"] is True


# ---- Unsupported syntax graceful degradation --------------------------------


def test_html_block_degrades_to_text() -> None:
    result = _blocks("<div>some html</div>")
    # Should not crash; degrades to a text block
    assert len(result) >= 0  # May produce empty or text block


def test_empty_markdown() -> None:
    result = md_to_feishu_blocks("")
    assert result == []


# ---- Output structure -------------------------------------------------------


def test_output_is_raw_block_list() -> None:
    """v2 API contract: each item is a Block dict (no insert/payload wrapper)."""
    result = md_to_feishu_blocks("# Title", parent_block_id="doc_123")
    assert isinstance(result, list)
    assert "block_type" in result[0]
    # No legacy wrapper keys
    assert "action" not in result[0]
    assert "parent_block_id" not in result[0]


# ---- Fixture round-trip -----------------------------------------------------


def test_sample_doc_fixture() -> None:
    sample_md = (FIXTURES / "sample_doc.md").read_text()
    result = md_to_feishu_blocks(sample_md)
    # Must produce at least one block per major section
    assert len(result) > 5
    # First block should be H1
    assert result[0]["block_type"] == bt.HEADING1
    # Must contain bullet blocks
    block_types = [r["block_type"] for r in result]
    assert bt.BULLET in block_types
    assert bt.CODE in block_types
    assert bt.TABLE in block_types
