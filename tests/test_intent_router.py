"""Unit tests for the intent classifier."""

import pytest

from app.services.intent_router import classify


@pytest.mark.parametrize(
    "text",
    [
        "生成PPT",
        "帮我生成 PPT",
        "请生成幻灯片",
        "生成文档",
        "生成会议纪要",
        "生成纪要",
        "/demo",
        "DEMO",
        "我想看示例文档",
    ],
)
def test_demo_triggers(text: str) -> None:
    assert classify(text) == "generate_demo"


@pytest.mark.parametrize(
    "text",
    [
        "你好",
        "今天天气怎么样",
        "What time is it?",
        "PPT 是什么意思？",  # mentions PPT but not as a command
        "",
        "   ",
    ],
)
def test_chat_default(text: str) -> None:
    assert classify(text) == "chat"


def test_case_insensitive() -> None:
    assert classify("DEMO") == "generate_demo"
    assert classify("Demo") == "generate_demo"


def test_whitespace_stripped() -> None:
    assert classify("   生成PPT   ") == "generate_demo"
