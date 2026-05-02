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


# ── S3-T09 new samples ────────────────────────────────────────────────────────


def test_sanitize_removes_technical_word_sentence() -> None:
    """Sentences containing LLM technical terms are filtered out."""
    text = "正在分析任务。intent score is 0.8, ambiguity high。继续执行。"
    result = sanitize(text)
    assert "intent" not in result
    assert "ambiguity" not in result
    assert "正在分析任务" in result
    assert "继续执行" in result


def test_sanitize_removes_filler_opener_sentence() -> None:
    """Sentences starting with 作为/根据/我理解 are removed."""
    text = "根据您的输入，我判断任务类型为文档。正在为您生成。"
    result = sanitize(text)
    assert "根据您的输入" not in result
    assert "正在为您生成" in result


def test_sanitize_strips_thinking_block() -> None:
    """<thinking> blocks are fully removed before other processing."""
    text = "<thinking>intent=create_new, score=0.9, 这个用户想要文档</thinking>正在生成文档大纲。"
    result = sanitize(text)
    assert "<thinking>" not in result
    assert "intent" not in result
    assert "这个用户" not in result
    assert "正在生成文档大纲" in result


def test_sanitize_blacklist_keyword_replaced() -> None:
    """Blacklisted phrases are replaced with safe alternatives."""
    text = "这个需求有些奇怪，但不合理的输入也要处理。"
    result = sanitize(text)
    assert "奇怪" not in result
    assert "不合理" not in result
    assert "正在分析中..." in result


def test_sanitize_long_text_truncated() -> None:
    """Text longer than 60 chars is truncated with an ellipsis."""
    text = "正在" + "分析" * 30  # well over 60 chars, no filtered content
    result = sanitize(text)
    assert len(result) <= 61  # 60 chars + "…"
    assert result.endswith("…")
