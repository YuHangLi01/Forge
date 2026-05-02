"""Stage 3 full demo rehearsal tests.

Marks: @pytest.mark.demo_critical
Run with: pytest -m demo_critical --no-cov -v

These tests validate the complete Stage 3 feature set using mocked LLM and Feishu,
ensuring demo readiness without incurring real API costs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.artifacts import DocArtifact, DocSection, PPTArtifact, SlideSchema
from app.schemas.enums import (
    ModificationType,
    OutputFormat,
    ScopeType,
    SlideLayout,
    TaskStatus,
    TaskType,
)
from app.schemas.intent import IntentSchema, ModificationIntent

# ── Shared fixtures ──────────────────────────────────────────────────────────


def _doc_artifact(n: int = 3) -> DocArtifact:
    return DocArtifact(
        doc_id="demo-doc-001",
        title="市场分析报告",
        sections=[
            DocSection(id=f"s{i}", title=f"章节{i + 1}", content_md=f"内容{i + 1}")
            for i in range(n)
        ],
        share_url="https://feishu.test/doc-demo",
    )


def _ppt_artifact(n: int = 4) -> PPTArtifact:
    return PPTArtifact(
        ppt_id="demo-ppt-001",
        title="市场分析PPT",
        slides=[
            SlideSchema(
                page_index=i,
                layout=SlideLayout.title_content,
                title=f"第{i + 1}页",
                bullets=[f"要点{i + 1}.1", f"要点{i + 1}.2"],
                speaker_notes="",
            )
            for i in range(n)
        ],
        share_url="https://feishu.test/ppt-demo",
    )


def _base_state(**overrides) -> dict:
    state = {
        "task_id": "demo_task",
        "user_id": "demo_user",
        "chat_id": "demo_chat",
        "message_id": "demo_msg",
        "completed_steps": [],
        "modification_history": [],
        "pending_user_action": None,
        "status": TaskStatus.pending,
        "ppt": None,
        "doc": None,
        "ppt_brief": None,
        "ppt_slides": [],
        "plan": None,
        "_lego_scenarios": None,
    }
    state.update(overrides)
    return state


# ── Demo Scenario A: Doc pipeline ────────────────────────────────────────────


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_a_doc_pipeline() -> None:
    """Step 1: user requests a market analysis doc → doc pipeline completes."""
    from app.graph.nodes.feishu_doc_write import feishu_doc_write_node
    from app.schemas.doc_outline import DocOutline, DocOutlineSection

    fake_outline = DocOutline(
        document_title="市场分析报告",
        sections=[
            DocOutlineSection(id="s1", title="市场现状"),
            DocOutlineSection(id="s2", title="竞争格局"),
            DocOutlineSection(id="s3", title="机会与风险"),
        ],
    )

    fake_doc = _doc_artifact(3)

    state = _base_state(
        normalized_text="帮我写一份市场分析报告，面向高管，专业简洁",
        doc_outline=fake_outline,
        doc_sections={"s1": "市场现状内容", "s2": "竞争格局内容", "s3": "机会内容"},
        doc_markdown=(
            "# 市场分析报告\n\n## 市场现状\n市场现状内容\n\n"
            "## 竞争格局\n竞争格局内容\n\n## 机会与风险\n机会内容"
        ),
    )

    with (
        patch(
            "app.services.feishu_doc_service.FeishuDocService.create_from_markdown",
            new_callable=AsyncMock,
            return_value=fake_doc,
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=AsyncMock()),
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster",
            return_value=MagicMock(emit_artifact=MagicMock(), begin_node=MagicMock()),
        ),
        patch("redis.asyncio.from_url") as mock_redis,
    ):
        mock_redis.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(setex=AsyncMock()))
        mock_redis.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await feishu_doc_write_node(state)

    assert result["status"] == TaskStatus.completed
    assert result["doc"].doc_id == "demo-doc-001"
    assert len(result["doc"].sections) >= 3


# ── Demo Scenario B: PPT pipeline ────────────────────────────────────────────


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_b_ppt_pipeline() -> None:
    """Step 2: user requests a PPT → ppt pipeline completes with ≥3 slides."""
    from app.graph.nodes.feishu_ppt_write import feishu_ppt_write_node

    fake_artifact = _ppt_artifact(4)
    ppt_brief = {
        "title": "市场分析PPT",
        "slide_count": 4,
        "audience": "高管",
        "style": "专业简洁",
    }
    ppt_slides = [
        {
            "slide_index": 0,
            "page_type": "cover",
            "title": "封面",
            "content": {"heading": "市场分析PPT", "subheading": "2026 Q1", "speaker_notes": ""},
        },
        {
            "slide_index": 1,
            "page_type": "content",
            "title": "市场现状",
            "content": {"heading": "市场现状", "bullets": ["要点1", "要点2"], "speaker_notes": ""},
        },
        {
            "slide_index": 2,
            "page_type": "content",
            "title": "竞争分析",
            "content": {"heading": "竞争分析", "bullets": ["要点A", "要点B"], "speaker_notes": ""},
        },
        {
            "slide_index": 3,
            "page_type": "closing",
            "title": "结论",
            "content": {"heading": "结论", "subheading": "Q&A", "speaker_notes": ""},
        },
    ]

    state = _base_state(ppt_brief=ppt_brief, ppt_slides=ppt_slides)

    with (
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new_callable=AsyncMock,
            return_value=fake_artifact,
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=AsyncMock()),
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster",
            return_value=MagicMock(emit_artifact=MagicMock()),
        ),
        patch("redis.asyncio.from_url") as mock_redis,
    ):
        mock_redis.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(setex=AsyncMock()))
        mock_redis.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await feishu_ppt_write_node(state)

    assert result["status"] == TaskStatus.completed
    assert len(result["ppt"].slides) >= 3
    assert result["ppt"].share_url == "https://feishu.test/ppt-demo"


# ── Demo Scenario C: Lego multi-format ───────────────────────────────────────


@pytest.mark.demo_critical
def test_demo_scenario_c_lego_cd_plan() -> None:
    """Step 3: multi-format request → lego plan chains C→D strictly serial."""
    from app.graph.nodes.lego_orchestrator import compose_plan

    plan = compose_plan(["C", "D"])
    nodes = [s.node_name for s in plan.steps]

    assert nodes[:3] == ["doc_structure_gen", "doc_content_gen", "feishu_doc_write"]
    assert nodes[3:] == ["ppt_structure_gen", "ppt_content_gen", "feishu_ppt_write"]
    assert "C3" in plan.steps[3].depends_on


@pytest.mark.demo_critical
def test_demo_scenario_c_step_router_lego_routing() -> None:
    """step_router routes multi-format intent through lego path."""
    from app.graph.nodes.step_router import route

    intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="市场分析报告+PPT",
        output_formats=[OutputFormat.document, OutputFormat.presentation],
        ambiguity_score=0.0,
    )
    state = {
        "status": None,
        "pending_user_action": None,
        "intent": intent,
        "_lego_scenarios": ["C", "D"],
        "plan": None,
        "completed_steps": ["context_retrieval"],
        "clarify_answer": None,
        "clarify_count": 0,
        "mod_intent": None,
    }
    assert route(state) == "lego_orchestrator"


# ── Demo Scenario D: Pause/resume ────────────────────────────────────────────


@pytest.mark.demo_critical
def test_demo_scenario_d_pause_keywords() -> None:
    """'等等' and '暂停' trigger pause intent."""
    from app.graph.nodes.checkpoint_control import detect_control_intent

    assert detect_control_intent("等等，先停一下") == "pause"
    assert detect_control_intent("暂停") == "pause"
    assert detect_control_intent("继续") == "resume"
    assert detect_control_intent("取消") == "cancel"


@pytest.mark.demo_critical
def test_demo_scenario_d_pause_routes_to_checkpoint() -> None:
    """pending_user_action='pause' → step_router routes to checkpoint_control."""
    from app.graph.nodes.step_router import route

    state = {
        "status": None,
        "pending_user_action": "pause",
        "intent": None,
        "plan": None,
        "completed_steps": [],
    }
    assert route(state) == "checkpoint_control"


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_d_checkpoint_control_emits_card() -> None:
    """checkpoint_control emits pause card with correct status."""
    from app.graph.nodes.checkpoint_control import checkpoint_control_node

    fake_plan = MagicMock()
    fake_plan.steps = [
        MagicMock(node_name="doc_structure_gen"),
        MagicMock(node_name="doc_content_gen"),
    ]
    state = _base_state(
        message_id="demo_pause_msg",
        completed_steps=["doc_structure_gen"],
        plan=fake_plan,
    )

    with patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter:
        mock_inst = AsyncMock()
        MockAdapter.return_value = mock_inst
        result = await checkpoint_control_node(state)

    assert result["status"] == TaskStatus.waiting_human
    assert result["_pause_reason"] == "user_paused"
    mock_inst.reply_card.assert_awaited_once()


# ── Demo Scenario E: Slide edit ──────────────────────────────────────────────


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_e_slide_editor() -> None:
    """Step 5: 'change slide 2 to English' → ppt_slide_editor updates target slide."""
    from app.graph.nodes.ppt_slide_editor import ppt_slide_editor_node

    existing = _ppt_artifact(4)
    updated = _ppt_artifact(4)

    mod_intent = ModificationIntent(
        target="presentation",
        scope_type=ScopeType.specific_slide,
        scope_identifier="第2页",
        modification_type=ModificationType.rewrite,
        instruction="改成英文",
        ambiguity_high=False,
    )

    state = _base_state(ppt=existing, mod_intent=mod_intent)

    with (
        patch(
            "app.services.llm_service.LLMService.invoke",
            new_callable=AsyncMock,
            return_value='{"heading": "Market Slide", "bullets": ["Point 1"], "speaker_notes": ""}',
        ),
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new_callable=AsyncMock,
            return_value=updated,
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=AsyncMock()),
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster",
            return_value=MagicMock(emit_artifact=MagicMock()),
        ),
        patch("redis.asyncio.from_url") as mock_redis,
    ):
        mock_redis.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(setex=AsyncMock()))
        mock_redis.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await ppt_slide_editor_node(state)

    assert result["status"] == TaskStatus.completed
    assert len(result["modification_history"]) == 1
    assert result["modification_history"][0].scope_identifier == "第2页"


# ── Demo Scenario F: Calendar disambiguation ─────────────────────────────────


@pytest.mark.demo_critical
def test_demo_scenario_f_calendar_time_word_detection() -> None:
    """Calendar disambiguation fires on time words."""
    from app.services.calendar_context import has_time_word

    assert has_time_word("明天开会前整理一份简报") is True
    assert has_time_word("帮我写个报告") is False


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_f_calendar_degradation() -> None:
    """Calendar API failure degrades silently — intent still parsed via V1."""
    from app.graph.nodes.intent_parser import intent_parser_node
    from app.integrations.feishu.calendar import CalendarFetchError
    from app.schemas.intent import IntentSchema

    state = {
        "message_id": "demo_cal_msg",
        "user_id": "demo_user",
        "normalized_text": "明天开会前写份简报",
    }

    fake_intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="会议简报",
        output_formats=[OutputFormat.document],
        ambiguity_score=0.2,
    )

    with (
        patch(
            "app.integrations.feishu.calendar.FeishuCalendarClient.get_events_around",
            new_callable=AsyncMock,
            side_effect=CalendarFetchError("no permission"),
        ),
        patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock,
    ):
        mock.return_value = fake_intent
        result = await intent_parser_node(state)

    assert "intent" in result


# ── Demo Scenario G: Cross-product modification disambiguation ────────────────


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_g_mod_disambig_ppt_keyword() -> None:
    """'幻灯片' keyword → mod_intent target forced to presentation."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    fake_intent = ModificationIntent(
        target="document",
        scope_type=ScopeType.specific_section,
        scope_identifier="第2页",
        modification_type=ModificationType.rewrite,
        instruction="改成英文",
        ambiguity_high=False,
    )

    state = _base_state(
        doc=_doc_artifact(3),
        ppt=_ppt_artifact(4),
        normalized_text="把幻灯片第2页改成英文",
    )

    with patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock:
        mock.return_value = fake_intent
        result = await mod_intent_parser_node(state)

    assert result["mod_intent"].target == "presentation"


@pytest.mark.demo_critical
@pytest.mark.asyncio
async def test_demo_scenario_g_mod_disambig_triggers_clarify() -> None:
    """Ambiguous mod instruction triggers mod_target_clarify card."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    ambiguous = ModificationIntent(
        target="document",
        scope_type=ScopeType.specific_section,
        scope_identifier="第2部分",
        modification_type=ModificationType.rewrite,
        instruction="改一下",
        ambiguity_high=True,
    )

    state = _base_state(
        doc=_doc_artifact(3),
        ppt=_ppt_artifact(4),
        normalized_text="改一下第2个",
    )

    with (
        patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock,
        patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter,
    ):
        mock.return_value = ambiguous
        mock_inst = AsyncMock()
        MockAdapter.return_value = mock_inst
        result = await mod_intent_parser_node(state)

    assert result.get("pending_user_action", {}).get("kind") == "mod_target_clarify"
    mock_inst.reply_card.assert_awaited_once()
