"""Unit tests for ppt_structure_gen, ppt_content_gen, design_tokens, node whitelist."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.nodes._validators import (
    build_available_nodes_prompt,
    get_allowed_nodes,
)
from app.services.design_tokens import get_preset, list_presets, resolve_token

# ── design_tokens ────────────────────────────────────────────────────────────


class TestDesignTokens:
    def test_list_presets_has_five(self) -> None:
        presets = list_presets()
        assert len(presets) == 5
        expected = {"corporate", "tech_dark", "warm_narrative", "minimal", "data_driven"}
        assert set(presets) == expected

    def test_get_preset_corporate(self) -> None:
        token = get_preset("corporate")
        assert token.name == "corporate"
        assert token.primary_color.startswith("#")

    def test_get_preset_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_preset("nonexistent")

    def test_resolve_token_investor_audience(self) -> None:
        assert resolve_token("投资方路演").name == "corporate"

    def test_resolve_token_tech_audience(self) -> None:
        assert resolve_token("技术团队内部分享").name == "tech_dark"

    def test_resolve_token_data_audience(self) -> None:
        assert resolve_token("数据分析报告").name == "data_driven"

    def test_resolve_token_narrative_audience(self) -> None:
        assert resolve_token("品牌故事宣传").name == "warm_narrative"

    def test_resolve_token_unknown_falls_back_to_minimal(self) -> None:
        assert resolve_token("随便一些话").name == "minimal"

    def test_all_presets_have_required_fields(self) -> None:
        for name in list_presets():
            t = get_preset(name)
            assert t.font_title
            assert t.font_body
            assert 20 <= t.font_size_title <= 60
            assert 10 <= t.font_size_body <= 30


# ── node whitelist / validators ──────────────────────────────────────────────


class TestNodeWhitelist:
    def test_stage2_allows_doc_nodes(self) -> None:
        allowed = get_allowed_nodes(2)
        assert "doc_structure_gen" in allowed
        assert "doc_content_gen" in allowed
        assert "feishu_doc_write" in allowed

    def test_stage2_blocks_ppt_nodes(self) -> None:
        allowed = get_allowed_nodes(2)
        assert "ppt_structure_gen" not in allowed
        assert "ppt_content_gen" not in allowed
        assert "feishu_ppt_write" not in allowed

    def test_stage3_allows_ppt_nodes(self) -> None:
        allowed = get_allowed_nodes(3)
        assert "ppt_structure_gen" in allowed
        assert "ppt_content_gen" in allowed
        assert "feishu_ppt_write" in allowed

    def test_stage3_still_allows_doc_nodes(self) -> None:
        allowed = get_allowed_nodes(3)
        assert "doc_structure_gen" in allowed
        assert "feishu_doc_write" in allowed

    def test_stage4_same_as_stage3(self) -> None:
        assert get_allowed_nodes(4) == get_allowed_nodes(3)

    def test_build_prompt_stage2_no_ppt_lines(self) -> None:
        prompt = build_available_nodes_prompt(2)
        assert "ppt_structure_gen" not in prompt
        assert "doc_structure_gen" in prompt

    def test_build_prompt_stage3_has_ppt_lines(self) -> None:
        prompt = build_available_nodes_prompt(3)
        assert "ppt_structure_gen" in prompt
        assert "ppt_content_gen" in prompt
        assert "feishu_ppt_write" in prompt


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_slide(idx: int, ptype: str, title: str, bullets: list[str] | None = None) -> dict:
    return {
        "slide_index": idx,
        "page_type": ptype,
        "title": title,
        "bullet_points": bullets or [],
        "speaker_notes": "",
    }


# ── ppt_structure_gen node ───────────────────────────────────────────────────


class TestPptStructureGenNode:
    @pytest.mark.asyncio
    async def test_returns_ppt_brief(self) -> None:
        from app.schemas.ppt import PPTBriefSchema

        mock_brief = PPTBriefSchema(
            title="测试 PPT",
            target_audience="投资人",
            slides=[
                _make_slide(0, "cover", "封面"),
                _make_slide(1, "closing", "谢谢"),
            ],
        )

        patch_path = "app.services.llm_service.LLMService.structured"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_brief
            from app.graph.nodes.ppt_structure_gen import ppt_structure_gen_node

            result = await ppt_structure_gen_node(
                {
                    "task_id": "t1",
                    "user_id": "u1",
                    "intent": None,
                    "retrieved_context": [],
                }
            )

        assert "ppt_brief" in result
        brief = result["ppt_brief"]
        assert brief["title"] == "测试 PPT"
        assert len(brief["slides"]) == 2

    @pytest.mark.asyncio
    async def test_design_token_resolved_from_audience(self) -> None:
        from app.schemas.ppt import PPTBriefSchema

        mock_brief = PPTBriefSchema(
            title="技术分享",
            target_audience="技术团队",
            slides=[
                _make_slide(0, "cover", "封面"),
                _make_slide(1, "closing", "结束"),
            ],
            design_token_name="",  # empty — should be resolved
        )

        patch_path = "app.services.llm_service.LLMService.structured"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_brief
            from app.graph.nodes.ppt_structure_gen import ppt_structure_gen_node

            result = await ppt_structure_gen_node(
                {
                    "task_id": "t1",
                    "user_id": "u1",
                    "intent": None,
                    "retrieved_context": [],
                }
            )

        assert result["ppt_brief"]["design_token_name"] == "tech_dark"

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self) -> None:
        patch_path = "app.services.llm_service.LLMService.structured"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = RuntimeError("LLM timeout")
            from app.graph.nodes.ppt_structure_gen import ppt_structure_gen_node

            result = await ppt_structure_gen_node(
                {
                    "task_id": "t1",
                    "user_id": "u1",
                    "intent": None,
                    "retrieved_context": [],
                }
            )

        assert "ppt_brief" in result
        assert len(result["ppt_brief"]["slides"]) >= 3


# ── ppt_content_gen node ─────────────────────────────────────────────────────


class TestPptContentGenNode:
    def _make_state(self, n_slides: int = 3) -> dict:
        slides = [
            _make_slide(0, "cover", "封面"),
            _make_slide(1, "content", "内容页", ["要点1", "要点2"]),
            _make_slide(2, "closing", "谢谢"),
        ]
        return {
            "task_id": "t1",
            "user_id": "u1",
            "ppt_brief": {
                "title": "测试 PPT",
                "target_audience": "通用听众",
                "slides": slides[:n_slides],
                "design_token_name": "minimal",
            },
            "completed_slide_ids": [],
        }

    @pytest.mark.asyncio
    async def test_returns_all_slides(self) -> None:
        mock_content = json.dumps({"heading": "封面", "subheading": "", "speaker_notes": ""})

        patch_path = "app.services.llm_service.LLMService.invoke"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_content
            from app.graph.nodes.ppt_content_gen import ppt_content_gen_node

            result = await ppt_content_gen_node(self._make_state(3))

        assert "ppt_slides" in result
        assert len(result["ppt_slides"]) == 3

    @pytest.mark.asyncio
    async def test_slides_sorted_by_index(self) -> None:
        mock_content = json.dumps({"heading": "x", "bullets": [], "speaker_notes": ""})

        patch_path = "app.services.llm_service.LLMService.invoke"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_content
            from app.graph.nodes.ppt_content_gen import ppt_content_gen_node

            result = await ppt_content_gen_node(self._make_state(3))

        indices = [s["slide_index"] for s in result["ppt_slides"]]
        assert indices == sorted(indices)

    @pytest.mark.asyncio
    async def test_skip_completed_slides(self) -> None:
        state = self._make_state(3)
        state["completed_slide_ids"] = [0, 2]
        state["ppt_slides"] = [
            {"slide_index": 0, "page_type": "cover", "title": "封面 (cached)", "content": {}},
            {"slide_index": 2, "page_type": "closing", "title": "谢谢 (cached)", "content": {}},
        ]

        mock_content = json.dumps({"heading": "内容页", "bullets": ["a", "b"], "speaker_notes": ""})

        patch_path = "app.services.llm_service.LLMService.invoke"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_content
            from app.graph.nodes.ppt_content_gen import ppt_content_gen_node

            result = await ppt_content_gen_node(state)

        assert mock_llm.call_count == 1  # only the non-completed slide
        assert len(result["ppt_slides"]) == 3

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self) -> None:
        patch_path = "app.services.llm_service.LLMService.invoke"
        with patch(patch_path, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "this is not json"
            from app.graph.nodes.ppt_content_gen import ppt_content_gen_node

            result = await ppt_content_gen_node(self._make_state(1))

        assert "ppt_slides" in result
        slide = result["ppt_slides"][0]
        assert "slide_index" in slide


# ── _extract_resize_scale ─────────────────────────────────────────────────────


class TestExtractResizeScale:
    def setup_method(self) -> None:
        from app.graph.nodes.ppt_slide_editor import _extract_resize_scale

        self.fn = _extract_resize_scale

    def test_no_resize_keyword_returns_none(self) -> None:
        assert self.fn("把标题改成蓝色") is None
        assert self.fn("替换第3页文字") is None
        assert self.fn("") is None

    def test_gentle_shrink_yi_dian(self) -> None:
        assert self.fn("改小一点") == pytest.approx(0.75)
        assert self.fn("缩小一点") == pytest.approx(0.75)
        assert self.fn("缩小一些") == pytest.approx(0.75)
        assert self.fn("稍微缩小") == pytest.approx(0.75)

    def test_gentle_enlarge_yi_dian(self) -> None:
        assert self.fn("改大一点") == pytest.approx(1.25)
        assert self.fn("放大一点") == pytest.approx(1.25)
        assert self.fn("放大一些") == pytest.approx(1.25)

    def test_aggressive_shrink(self) -> None:
        assert self.fn("缩小很多") == pytest.approx(0.5)
        assert self.fn("大幅缩小") == pytest.approx(0.5)

    def test_aggressive_enlarge(self) -> None:
        assert self.fn("放大很多") == pytest.approx(1.6)
        assert self.fn("明显放大") == pytest.approx(1.6)

    def test_explicit_percent_shrink(self) -> None:
        assert self.fn("缩小30%") == pytest.approx(0.70)
        assert self.fn("缩小50%") == pytest.approx(0.50)

    def test_explicit_percent_enlarge(self) -> None:
        assert self.fn("放大20%") == pytest.approx(1.20)
        assert self.fn("放大50%") == pytest.approx(1.50)

    def test_scale_to_percent(self) -> None:
        assert self.fn("缩小到60%") == pytest.approx(0.60)
        assert self.fn("放大到150%") == pytest.approx(1.50)

    def test_yi_bei(self) -> None:
        assert self.fn("放大一倍") == pytest.approx(2.0)

    def test_default_moderate_shrink(self) -> None:
        assert self.fn("缩小") == pytest.approx(0.7)

    def test_default_moderate_enlarge(self) -> None:
        assert self.fn("放大") == pytest.approx(1.3)

    def test_english_shrink(self) -> None:
        assert self.fn("shrink the chart") == pytest.approx(0.7)

    def test_english_enlarge(self) -> None:
        assert self.fn("enlarge the chart") == pytest.approx(1.3)


# ── _parse_slide_index ────────────────────────────────────────────────────────


class TestParseSlideIndex:
    def setup_method(self) -> None:
        from app.graph.nodes.ppt_slide_editor import _parse_slide_index

        self.fn = _parse_slide_index

    def test_arabic_digit(self) -> None:
        assert self.fn("第1页") == 0
        assert self.fn("第5页") == 4
        assert self.fn("第10页") == 9

    def test_chinese_digit(self) -> None:
        assert self.fn("第三页") == 2
        assert self.fn("第五页") == 4

    def test_no_match_returns_zero(self) -> None:
        assert self.fn("全部幻灯片") == 0
        assert self.fn("") == 0


# ── ChartSchema width/height defaults ────────────────────────────────────────


class TestChartSchemaSize:
    def test_defaults(self) -> None:
        from app.schemas.artifacts import ChartSchema

        c = ChartSchema()
        assert c.width_inches == pytest.approx(9.0)
        assert c.height_inches == pytest.approx(4.5)

    def test_custom_size(self) -> None:
        from app.schemas.artifacts import ChartSchema

        c = ChartSchema(width_inches=6.0, height_inches=3.0)
        assert c.width_inches == pytest.approx(6.0)
        assert c.height_inches == pytest.approx(3.0)

    def test_coerce_column_to_bar(self) -> None:
        from app.schemas.artifacts import ChartSchema
        from app.schemas.enums import ChartType

        c = ChartSchema(chart_type="column")  # type: ignore[arg-type]
        assert c.chart_type == ChartType.bar


# ── normalize_modification_type new aliases ──────────────────────────────────


class TestModificationTypeAliases:
    def test_resize_element_maps_to_reformat(self) -> None:
        from app.schemas.enums import ModificationType
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="presentation",
            scope_type="specific_slide",
            scope_identifier="第5页",
            modification_type="resize_element",  # type: ignore[arg-type]
            instruction="缩小图表",
        )
        assert m.modification_type == ModificationType.reformat

    def test_shrink_maps_to_reformat(self) -> None:
        from app.schemas.enums import ModificationType
        from app.schemas.intent import ModificationIntent

        m = ModificationIntent(
            target="presentation",
            scope_type="specific_slide",
            scope_identifier="第5页",
            modification_type="shrink",  # type: ignore[arg-type]
            instruction="缩小图表",
        )
        assert m.modification_type == ModificationType.reformat

    def test_unknown_value_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        from app.schemas.intent import ModificationIntent

        with pytest.raises(ValidationError):
            ModificationIntent(
                target="presentation",
                scope_type="specific_slide",
                scope_identifier="第5页",
                modification_type="some_unknown_type",  # type: ignore[arg-type]
                instruction="test",
            )


# ── _is_chart_layout_op ───────────────────────────────────────────────────────


class TestIsChartLayoutOp:
    def setup_method(self) -> None:
        from app.graph.nodes.ppt_slide_editor import _is_chart_layout_op

        self.fn = _is_chart_layout_op

    # ── should be True (chart + resize) ──────────────────────────────────────
    def test_chart_resize_shrink(self) -> None:
        assert self.fn("缩小折线图") is True

    def test_chart_resize_enlarge(self) -> None:
        assert self.fn("放大图表") is True

    def test_chart_resize_english(self) -> None:
        assert self.fn("shrink the chart") is True

    # ── should be True (chart + reposition) ──────────────────────────────────
    def test_chart_reposition_no_overlap(self) -> None:
        assert self.fn("将折线图调整至无重叠区域") is True

    def test_chart_reposition_move(self) -> None:
        assert self.fn("把图表移动到下方") is True

    def test_chart_reposition_zhi_xia_fang(self) -> None:
        assert self.fn("将图表移至下方") is True

    def test_chart_reposition_wang_xia(self) -> None:
        assert self.fn("将图表往下挪") is True

    def test_chart_reposition_english(self) -> None:
        assert self.fn("reposition the chart") is True

    # ── should be False — regression guards ──────────────────────────────────
    def test_font_resize_no_chart_is_false(self) -> None:
        assert self.fn("缩小字体") is False

    def test_enlarge_title_no_chart_is_false(self) -> None:
        assert self.fn("放大标题文字") is False

    def test_shrink_text_no_chart_is_false(self) -> None:
        assert self.fn("shrink the font size") is False

    def test_delete_text_below_chart_is_false(self) -> None:
        # "下方" as spatial noun, not movement target — must NOT trigger layout op
        assert self.fn("将图表下方的注释删除") is False

    def test_add_text_below_chart_is_false(self) -> None:
        assert self.fn("在图表下方添加说明文字") is False

    def test_color_change_chart_is_false(self) -> None:
        # Style change on chart text — should go through LLM, not layout op
        assert self.fn("将折线图的标题改为蓝色") is False

    def test_empty_instruction_is_false(self) -> None:
        assert self.fn("") is False
