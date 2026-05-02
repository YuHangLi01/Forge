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
