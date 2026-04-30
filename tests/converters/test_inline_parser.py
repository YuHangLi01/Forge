from markdown_it import MarkdownIt

from app.converters.inline_parser import parse_inline_tokens

_md = MarkdownIt("commonmark")


def _parse(text: str) -> list[dict]:
    tokens = _md.parse(text)
    # Find the inline token inside paragraph
    for tok in tokens:
        if tok.type == "inline" and tok.children:
            return parse_inline_tokens(tok.children)
    return []


def _run(element: dict) -> dict:
    """Each element is a Feishu TextElement oneof: {'text_run': {...}}."""
    return element["text_run"]


def test_plain_text() -> None:
    els = _parse("Hello world")
    assert _run(els[0])["content"] == "Hello world"
    assert "text_element_style" not in _run(els[0])


def test_bold() -> None:
    els = _parse("**bold**")
    assert _run(els[0])["text_element_style"]["bold"] is True
    assert _run(els[0])["content"] == "bold"


def test_italic() -> None:
    els = _parse("*italic*")
    assert _run(els[0])["text_element_style"]["italic"] is True


def test_inline_code() -> None:
    els = _parse("`code`")
    assert _run(els[0])["text_element_style"]["inline_code"] is True
    assert _run(els[0])["content"] == "code"


def test_link() -> None:
    els = _parse("[text](https://example.com)")
    assert _run(els[0])["content"] == "text"
    assert _run(els[0])["text_element_style"]["link"]["url"] == "https://example.com"


def test_bold_italic_combined() -> None:
    els = _parse("**bold *italic* end**")
    texts = [_run(e)["content"] for e in els]
    joined = "".join(texts)
    assert "bold" in joined
    assert "italic" in joined


def test_empty_tokens() -> None:
    result = parse_inline_tokens([])
    assert result == []


def test_oneof_shape_is_text_run_only() -> None:
    """Each element must have exactly one of the recognised TextElement keys."""
    els = _parse("hi **there**")
    for e in els:
        assert "text_run" in e
        # Must not carry the legacy flat 'tag'/'content' top-level keys
        assert "tag" not in e
        assert "content" not in e
