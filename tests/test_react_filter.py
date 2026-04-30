"""Tests for ReAct filter: strip_thinking and sanitize."""

from app.services.react_filter import sanitize, strip_thinking


def test_strip_thinking_removes_thinking_tag() -> None:
    text = "intro <thinking>内部推理，不该给用户看</thinking> result"
    assert strip_thinking(text) == "intro  result"


def test_strip_thinking_removes_think_tag() -> None:
    text = "start <think>hidden</think> end"
    assert strip_thinking(text) == "start  end"


def test_strip_thinking_case_insensitive() -> None:
    text = "<THINKING>caps</THINKING>ok"
    assert strip_thinking(text) == "ok"


def test_strip_thinking_multiline() -> None:
    text = "before\n<thinking>\nline1\nline2\n</thinking>\nafter"
    assert "line1" not in strip_thinking(text)
    assert "after" in strip_thinking(text)


def test_strip_thinking_no_tags_unchanged() -> None:
    text = "正常回复内容，没有思考块"
    assert strip_thinking(text) == text


def test_sanitize_replaces_banned_phrase() -> None:
    text = "用户的输入很奇怪，我需要重新理解"
    result = sanitize(text)
    assert "用户的输入很奇怪" not in result
    assert "正在分析中..." in result


def test_sanitize_strips_thinking_then_replaces() -> None:
    text = "<thinking>这个用户想要什么</thinking>好的，正在处理"
    result = sanitize(text)
    assert "<thinking>" not in result
    assert "这个用户" not in result


def test_sanitize_removes_ai_self_reference() -> None:
    text = "作为AI，我可以帮助您处理这个请求。"
    result = sanitize(text)
    assert "作为AI" not in result


def test_sanitize_clean_text_unchanged() -> None:
    text = "正在为您生成文档，请稍候..."
    assert sanitize(text) == text


def test_sanitize_empty_string() -> None:
    assert sanitize("") == ""
