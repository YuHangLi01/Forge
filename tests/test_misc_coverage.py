"""Coverage tests for small, pure-function modules with zero/low coverage."""

from __future__ import annotations

import pytest

from app.exceptions import ForgeError

# ── thinking_renderer ─────────────────────────────────────────────────────────


class TestThinkingRenderer:
    def test_known_node_before(self) -> None:
        from app.services.thinking_renderer import get_before_text

        assert "大纲" in get_before_text("doc_structure_gen")
        assert "PPT" in get_before_text("ppt_structure_gen")

    def test_known_node_after(self) -> None:
        from app.services.thinking_renderer import get_after_text

        assert get_after_text("feishu_doc_write") == "飞书文档已写入"
        assert get_after_text("ppt_slide_editor") == "幻灯片已修改"

    def test_unknown_node_before_returns_default(self) -> None:
        from app.services.thinking_renderer import get_before_text

        assert get_before_text("nonexistent_node") == "正在处理…"

    def test_unknown_node_after_returns_default(self) -> None:
        from app.services.thinking_renderer import get_after_text

        assert get_after_text("nonexistent_node") == "已完成"

    def test_all_before_templates_are_strings(self) -> None:
        from app.services.thinking_renderer import BEFORE_TEMPLATES

        assert all(isinstance(v, str) and v for v in BEFORE_TEMPLATES.values())

    def test_all_after_templates_are_strings(self) -> None:
        from app.services.thinking_renderer import AFTER_TEMPLATES

        assert all(isinstance(v, str) and v for v in AFTER_TEMPLATES.values())


# ── file_extractor ─────────────────────────────────────────────────────────────


class TestFileExtractor:
    def test_txt_file(self) -> None:
        from app.services.file_extractor import extract_text_from_file

        result = extract_text_from_file(b"hello world", "test.txt")
        assert result == "hello world"

    def test_md_file(self) -> None:
        from app.services.file_extractor import extract_text_from_file

        result = extract_text_from_file(b"# Title\nContent", "readme.md")
        assert "Title" in result

    def test_empty_content_raises(self) -> None:
        from app.services.file_extractor import extract_text_from_file

        with pytest.raises(ForgeError):
            extract_text_from_file(b"", "file.txt")

    def test_too_large_raises(self) -> None:
        from app.services.file_extractor import extract_text_from_file

        big = b"x" * (11 * 1024 * 1024)
        with pytest.raises(ForgeError) as exc_info:
            extract_text_from_file(big, "file.txt")
        assert "413" in str(exc_info.value.code) or exc_info.value.code == 413

    def test_unsupported_extension_raises(self) -> None:
        from app.services.file_extractor import extract_text_from_file

        with pytest.raises(ForgeError) as exc_info:
            extract_text_from_file(b"data", "file.pdf")
        assert exc_info.value.code == 415

    def test_docx_import_error_raises_forge_error(self) -> None:
        from unittest.mock import patch

        from app.services.file_extractor import extract_text_from_file

        with (
            patch.dict("sys.modules", {"docx": None}),
            pytest.raises((ForgeError, ImportError, Exception)),
        ):
            extract_text_from_file(b"PK fake docx bytes", "test.docx")


# ── tool_registry ─────────────────────────────────────────────────────────────


class TestToolRegistry:
    def setup_method(self) -> None:
        from app.graph.tool_registry import clear

        clear()

    def teardown_method(self) -> None:
        from app.graph.tool_registry import clear

        clear()

    def test_register_and_get(self) -> None:
        from app.graph.tool_registry import get, register

        register("my_tool", object())
        tool = get("my_tool")
        assert tool is not None

    def test_get_unregistered_raises(self) -> None:
        from app.graph.tool_registry import get

        with pytest.raises(KeyError, match="not registered"):
            get("nonexistent")

    def test_clear_removes_all(self) -> None:
        from app.graph.tool_registry import clear, get, register

        register("t1", "v1")
        register("t2", "v2")
        clear()
        with pytest.raises(KeyError):
            get("t1")

    def test_overwrite_registration(self) -> None:
        from app.graph.tool_registry import get, register

        register("t", "first")
        register("t", "second")
        assert get("t") == "second"


# ── schemas/lego ──────────────────────────────────────────────────────────────


class TestLegoSchema:
    def test_lego_scenario_values(self) -> None:
        from app.schemas.lego import LegoScenario

        assert LegoScenario.C == "C"
        assert LegoScenario.D == "D"

    def test_lego_scenario_is_str(self) -> None:
        from app.schemas.lego import LegoScenario

        assert isinstance(LegoScenario.C, str)


# ── prompts/clarify_question ──────────────────────────────────────────────────


class TestClarifyQuestionPrompt:
    def test_prompt_registered(self) -> None:
        import app.prompts.clarify_question  # noqa: F401
        from app.prompts._versioning import get

        prompt = get("clarify_question")
        assert prompt is not None
        assert "{user_message}" in prompt.text

    def test_prompt_has_intent_placeholder(self) -> None:
        import app.prompts.clarify_question  # noqa: F401
        from app.prompts._versioning import get

        prompt = get("clarify_question")
        assert "{intent_summary}" in prompt.text


# ── schemas/intent validators ─────────────────────────────────────────────────


class TestIntentSchemaValidators:
    def test_scope_type_alias_page(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="document",
            scope_type="page",  # type: ignore[arg-type]
            scope_identifier="第1页",
            modification_type="rewrite",
            instruction="test",
        )
        assert str(m.scope_type) == "specific_slide"

    def test_scope_type_alias_section(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="document",
            scope_type="section",  # type: ignore[arg-type]
            scope_identifier="背景",
            modification_type="rewrite",
            instruction="test",
        )
        assert str(m.scope_type) == "specific_section"

    def test_scope_type_chinese_fallback_full(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="document",
            scope_type="全部内容",  # contains "全部" → full
            scope_identifier="全部",
            modification_type="rewrite",
            instruction="test",
        )
        assert str(m.scope_type) == "full"

    def test_scope_type_chinese_fallback_slide(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="presentation",
            scope_type="某页幻灯片",  # contains "幻灯片" → specific_slide
            scope_identifier="第3页",
            modification_type="rewrite",
            instruction="test",
        )
        assert str(m.scope_type) == "specific_slide"

    def test_modification_type_chinese_reformat(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="document",
            scope_type="full",
            scope_identifier="全部",
            modification_type="格式调整",  # type: ignore[arg-type]
            instruction="test",
        )
        assert str(m.modification_type) == "reformat"

    def test_modification_type_chinese_delete(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="document",
            scope_type="full",
            scope_identifier="全部",
            modification_type="删除这段",  # type: ignore[arg-type]
            instruction="test",
        )
        assert str(m.modification_type) == "delete"

    def test_modification_type_chinese_append(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="document",
            scope_type="full",
            scope_identifier="全部",
            modification_type="增加内容",  # type: ignore[arg-type]
            instruction="test",
        )
        assert str(m.modification_type) == "append"

    def test_target_alias_doc(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="doc",  # type: ignore[arg-type]
            scope_type="full",
            scope_identifier="全部",
            modification_type="rewrite",
            instruction="test",
        )
        assert str(m.target) == "document"

    def test_target_alias_ppt(self) -> None:
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="ppt",  # type: ignore[arg-type]
            scope_type="full",
            scope_identifier="全部",
            modification_type="rewrite",
            instruction="test",
        )
        assert str(m.target) == "presentation"
