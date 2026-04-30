"""Parse markdown-it inline token sequences into Feishu text_run elements."""

from typing import Any

from markdown_it.token import Token


def parse_inline_tokens(tokens: list[Token]) -> list[dict[str, Any]]:
    """Convert a list of inline tokens into Feishu text_run elements."""
    elements: list[dict[str, Any]] = []
    _bold = False
    _italic = False
    _code = False
    _link_href = ""

    for tok in tokens:
        if tok.type == "softbreak" or tok.type == "hardbreak":
            elements.append(_text_run("\n", bold=_bold, italic=_italic))
        elif tok.type == "code_inline":
            elements.append(_text_run(tok.content, inline_code=True))
        elif tok.type == "strong_open":
            _bold = True
        elif tok.type == "strong_close":
            _bold = False
        elif tok.type == "em_open":
            _italic = True
        elif tok.type == "em_close":
            _italic = False
        elif tok.type == "link_open":
            attrs = dict(tok.attrs or {})
            _link_href = str(attrs.get("href", ""))
        elif tok.type == "link_close":
            _link_href = ""
        elif tok.type == "text":
            if _link_href:
                elements.append(_link_run(tok.content, _link_href))
            else:
                elements.append(_text_run(tok.content, bold=_bold, italic=_italic, code=_code))
        elif tok.type == "html_inline":
            # Degrade HTML inline to plain text
            elements.append(_text_run(tok.content))

    return [e for e in elements if _content(e) != ""]


def _content(element: dict[str, Any]) -> str:
    """Extract the text content from a text_run-style element (oneof shape)."""
    run = element.get("text_run") or {}
    if isinstance(run, dict):
        return str(run.get("content", ""))
    return ""


def _text_run(
    content: str,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    inline_code: bool = False,
) -> dict[str, Any]:
    """Return a Feishu docx v1 TextElement with a text_run oneof.

    Schema (from lark-oapi TextElement / TextRun): each element is a
    *single* oneof key (``text_run``, ``mention_user``, ``link_preview``…)
    whose value carries ``content`` and ``text_element_style``.
    The flat ``{"tag": "text_run", "content": ...}`` shape used previously
    was rejected by Feishu with code 99992402 'field validation failed'.
    """
    style: dict[str, Any] = {}
    if bold:
        style["bold"] = True
    if italic:
        style["italic"] = True
    if inline_code or code:
        style["inline_code"] = True
    text_run: dict[str, Any] = {"content": content}
    if style:
        text_run["text_element_style"] = style
    return {"text_run": text_run}


def _link_run(content: str, href: str) -> dict[str, Any]:
    return {
        "text_run": {
            "content": content,
            "text_element_style": {"link": {"url": href}},
        }
    }
