"""12-step DEMO scenario tests — mock-based, no live infra required.

Each test corresponds to one step in the Stage-3 demo script.
All LLM / Feishu / ChromaDB / Redis calls are mocked.

Markers: @pytest.mark.demo_critical
Run with: uv run pytest tests/e2e/scenarios/ -m demo_critical -v --no-cov
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.graph.nodes.step_router import route
from app.schemas.enums import OutputFormat, TaskStatus, TaskType
from app.schemas.intent import IntentSchema
from tests.e2e.scenarios.conftest import (
    DEMO_CHAT_ID,
    DEMO_USER_ID,
    _base_state,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_graph_mock(state_values: dict | None = None):
    """Graph mock compatible with card-task handler tests."""
    graph = AsyncMock()
    state = MagicMock()
    state.values = state_values or {}
    graph.aget_state = AsyncMock(return_value=state)
    graph.aupdate_state = AsyncMock(return_value=None)
    graph.ainvoke = AsyncMock(return_value={"status": "completed"})
    return graph


def _make_redis_mock(acquired_sequence: list):
    """Async context manager mock for redis.asyncio.from_url with SETNX behaviour."""
    r = AsyncMock()
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    r.set = AsyncMock(side_effect=acquired_sequence)
    return r


# ── Step 1 — 语音 + 日历查询 + 主动澄清 ─────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step01_calendar_query_triggers_clarify(demo_calendar_events) -> None:
    """intent_parser fetches calendar events and returns a high-ambiguity intent.

    step_router should subsequently route to clarify_question.
    """
    from app.graph.nodes.intent_parser import intent_parser_node

    high_ambiguity_intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="帮我准备复盘材料",
        output_formats=[OutputFormat.document],
        ambiguity_score=0.85,
        missing_info=["日期", "受众"],
    )

    state = _base_state(normalized_text="帮我准备明天的复盘材料")

    with (
        patch(
            "app.integrations.feishu.calendar.FeishuCalendarClient.get_events_around",
            new=AsyncMock(return_value=demo_calendar_events),
        ),
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=high_ambiguity_intent),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now") as mock_send_now,
    ):
        result = await intent_parser_node(state)

    assert result["intent"].ambiguity_score >= 0.7

    router_state = {**state, "intent": result["intent"]}
    assert route(router_state) == "clarify_question"

    # emit_tool_use("飞书日历查询", ...) calls _send_now with a card dict
    call_strs = [str(c) for c in mock_send_now.call_args_list]
    assert any("飞书日历查询" in s for s in call_strs)


# ── Step 2 — 澄清确认 + 历史检索 + 计划预览 ──────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step02_clarify_confirm_triggers_rag_and_plan_preview(
    demo_intent, demo_rag_results, demo_plan
) -> None:
    """context_retrieval returns 3 chunks; planner emits plan_confirm gate."""
    from app.graph.nodes.context_retrieval import context_retrieval_node
    from app.graph.nodes.planner import planner_node

    state = _base_state(intent=demo_intent)

    with (
        patch(
            "app.services.chroma_service.ChromaService.query",
            new=AsyncMock(return_value=demo_rag_results),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
    ):
        ctx = await context_retrieval_node(state)

    assert len(ctx["retrieved_context"]) == 3
    assert "context_retrieval" in ctx["completed_steps"]

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=demo_plan),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
        patch(
            "app.services.progress_broadcaster.ProgressBroadcaster.emit_plan_preview"
        ) as mock_plan_preview,
    ):
        plan_result = await planner_node({**state, **ctx})

    assert len(plan_result["plan"].steps) == 6
    assert plan_result["pending_user_action"]["kind"] == "plan_confirm"
    assert plan_result["status"] == TaskStatus.waiting_human
    mock_plan_preview.assert_called_once()


# ── Step 3 — 执行主链路 (doc + ppt + delivery) ───────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step03_plan_confirm_executes_full_pipeline(
    memory_graph, demo_intent, demo_plan, demo_doc_artifact, demo_ppt_artifact
) -> None:
    """Full doc+ppt pipeline completes with status=completed and both artifacts."""
    from app.schemas.doc_outline import DocOutline, DocOutlineSection
    from app.schemas.ppt import PPTBriefSchema, SlideBrief

    titles = ["总结", "问题", "行动", "展望"]
    doc_outline = DocOutline(
        document_title="Q3复盘汇报",
        sections=[DocOutlineSection(id=f"s{i}", title=t) for i, t in enumerate(titles)],
    )
    ppt_brief = PPTBriefSchema(
        title="Q3复盘汇报",
        target_audience="VP",
        slides=[
            SlideBrief(slide_index=i, page_type="content", title=f"第{i + 1}页") for i in range(7)
        ],
    )

    state = _base_state(
        intent=demo_intent,
        plan=demo_plan,
        retrieved_context=[
            {"text": "背景资料", "metadata": {}, "distance": 0.1},
        ],
        completed_steps=["preprocess", "context_retrieval"],
    )

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(side_effect=[doc_outline, ppt_brief]),
        ),
        patch(
            "app.services.llm_service.LLMService.invoke",
            new=AsyncMock(return_value='{"heading": "标题", "bullets": ["要点A", "要点B"]}'),
        ),
        patch(
            "app.services.feishu_doc_service.FeishuDocService.create_from_markdown",
            new=AsyncMock(return_value=demo_doc_artifact),
        ),
        patch(
            "app.services.ppt_service.PPTService.create_from_outline",
            new=AsyncMock(return_value=demo_ppt_artifact),
        ),
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=AsyncMock()),
        patch("app.integrations.feishu.adapter.FeishuAdapter.send_card", new=AsyncMock()),
        patch(
            "app.integrations.feishu.adapter.FeishuAdapter.set_permission_public",
            new=AsyncMock(),
        ),
        patch(
            "app.integrations.feishu.wiki.FeishuWikiClient.create_node",
            new=AsyncMock(return_value="wiki_node_demo"),
        ),
        patch(
            "app.integrations.feishu.wiki.FeishuWikiClient.share_url",
            return_value="https://feishu.cn/wiki/demo",
        ),
        patch("app.services.artifact_indexer.ArtifactIndexer.index_delivery", new=AsyncMock()),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_artifact"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.emit_plan_preview"),
        patch("redis.asyncio.from_url", return_value=_make_redis_mock([None])),
    ):
        final = await memory_graph.ainvoke(
            state,
            config={"configurable": {"thread_id": "demo-step3"}},
        )

    assert final["status"] == TaskStatus.completed
    assert final.get("doc") is not None
    assert final.get("ppt") is not None
    assert "delivery_node" in (final.get("completed_steps") or [])


# ── Step 4 — Agent 运行时改主意 (mid_execution_replanner) ─────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step04_low_quality_score_triggers_replanner_adds_slide(
    demo_intent, demo_plan, demo_rag_results
) -> None:
    """After ppt_structure_gen, low quality_score inserts mid_execution_replanner."""
    from app.graph.nodes.mid_execution_replanner import mid_execution_replanner_node
    from app.schemas.replan import ReplanDecision

    router_state = _base_state(
        intent=demo_intent,
        plan=demo_plan,
        quality_score=0.45,
        completed_steps=[
            "context_retrieval",
            "doc_structure_gen",
            "doc_content_gen",
            "feishu_doc_write",
            "ppt_structure_gen",
        ],
    )
    assert route(router_state) == "mid_execution_replanner"

    ppt_brief_dict = {
        "title": "Q3复盘汇报",
        "target_audience": "VP",
        "slides": [
            {
                "slide_index": i,
                "page_type": "content",
                "title": f"第{i + 1}页",
                "bullet_points": [f"要点{i}"],
                "speaker_notes": "",
            }
            for i in range(7)
        ],
    }

    decision = ReplanDecision(
        should_add=True,
        slide_title="v3.2.1时间线分析",
        bullet_points=["版本延迟3周", "影响DAU峰值"],
    )

    state = _base_state(
        ppt_brief=ppt_brief_dict,
        retrieved_context=demo_rag_results,
        quality_score=0.45,
    )

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=decision),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster.update_thinking"),
    ):
        result = await mid_execution_replanner_node(state)

    assert "mid_execution_replanner" in result["completed_steps"]
    new_slides = result["ppt_brief"]["slides"]
    assert len(new_slides) == 8
    assert new_slides[2]["title"] == "v3.2.1时间线分析"


# ── Step 5 — 战报 + 知识库归档 + @mention ─────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step05_delivery_sends_battle_report_with_mentions_and_wiki(
    demo_intent, demo_doc_artifact, demo_ppt_artifact, demo_rag_results, demo_plan
) -> None:
    """delivery_node archives to wiki, indexes to ChromaDB, and sends battle report card."""
    from app.graph.nodes.delivery_node import delivery_node_node

    state = _base_state(
        intent=demo_intent,
        doc=demo_doc_artifact,
        ppt=demo_ppt_artifact,
        retrieved_context=demo_rag_results,
        plan=demo_plan,
        completed_steps=["feishu_doc_write", "feishu_ppt_write"],
    )

    mock_reply_card = AsyncMock()
    mock_index_delivery = AsyncMock()

    with (
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=mock_reply_card),
        patch(
            "app.integrations.feishu.wiki.FeishuWikiClient.create_node",
            new=AsyncMock(return_value="wiki_node_abc"),
        ),
        patch(
            "app.integrations.feishu.wiki.FeishuWikiClient.share_url",
            return_value="https://feishu.cn/wiki/wiki_node_abc",
        ),
        patch(
            "app.services.artifact_indexer.ArtifactIndexer.index_delivery",
            new=mock_index_delivery,
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
    ):
        result = await delivery_node_node(state)
        # Let the fire-and-forget ensure_future task run
        await asyncio.sleep(0)

    assert result["status"] == TaskStatus.completed
    assert "delivery_node" in result["completed_steps"]

    mock_reply_card.assert_awaited()
    card_str = str(mock_reply_card.call_args_list)
    assert "lina_001" in card_str
    assert "chenlei_002" in card_str

    mock_index_delivery.assert_awaited_once()
    kw = mock_index_delivery.call_args.kwargs
    assert kw["user_id"] == DEMO_USER_ID


# ── Step 6 — 对话式修改 (PPT 第 3 页) ────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step06_text_command_modifies_ppt_page3(
    demo_intent, demo_doc_artifact, demo_ppt_artifact
) -> None:
    """mod_intent_parser parses 'PPT第3页' instruction and routes to ppt_slide_editor."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node
    from app.schemas.intent import ModificationIntent

    mod_intent = ModificationIntent(
        target=OutputFormat.presentation,
        scope_type="specific_slide",
        scope_identifier="第3页",
        modification_type="rewrite",
        instruction="改为柱状图，标题改成问题根因分析",
    )

    mod_state = _base_state(
        normalized_text="把PPT第3页改成柱状图，标题改成问题根因分析",
        intent=IntentSchema(
            task_type=TaskType.modify_existing,
            primary_goal="修改PPT第3页",
            output_formats=[OutputFormat.presentation],
            ambiguity_score=0.1,
        ),
        doc=demo_doc_artifact,
        ppt=demo_ppt_artifact,
        modification_history=[],
        completed_steps=["prior_artifact_retrieval"],
    )

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=mod_intent),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
    ):
        result = await mod_intent_parser_node(mod_state)

    mod = result["mod_intent"]
    assert str(mod.target) == "presentation"
    assert mod.scope_identifier == "第3页"
    assert "根因" in mod.instruction

    route_state = {**mod_state, "mod_intent": mod}
    assert route(route_state) == "ppt_slide_editor"


# ── Step 7 — 多轮修改引用 ("刚才改的那段") ───────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step07_history_reference_resolves_to_ppt_page3(
    demo_doc_artifact, demo_ppt_artifact
) -> None:
    """mod_intent_parser resolves history reference ('刚才那段') to slide 3."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node
    from app.schemas.intent import ModificationIntent
    from app.schemas.modification import ModificationRecord

    prev_record = ModificationRecord(
        step_index=0,
        target="presentation",
        scope_identifier="第3页",
        instruction="改为柱状图",
        before_summary="原始第3页内容摘要",
        after_summary="柱状图版第3页内容摘要",
    )

    follow_up_mod = ModificationIntent(
        target=OutputFormat.presentation,
        scope_type="specific_slide",
        scope_identifier="第3页",
        modification_type="append",
        instruction="追加数据来源：Q3监测报告",
    )

    state = _base_state(
        normalized_text="刚才改的那段加上数据来源",
        intent=IntentSchema(
            task_type=TaskType.modify_existing,
            primary_goal="追加数据来源",
            output_formats=[OutputFormat.presentation],
            ambiguity_score=0.2,
        ),
        doc=demo_doc_artifact,
        ppt=demo_ppt_artifact,
        modification_history=[prev_record],
        completed_steps=["prior_artifact_retrieval"],
    )

    with (
        patch(
            "app.services.llm_service.LLMService.structured",
            new=AsyncMock(return_value=follow_up_mod),
        ),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
    ):
        result = await mod_intent_parser_node(state)

    mod2 = result["mod_intent"]
    assert mod2.scope_identifier == "第3页"
    assert str(mod2.target) == "presentation"
    assert "数据来源" in mod2.instruction


# ── Step 8 — 多端幂等 (第 2 次点击返回 duplicate) ────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step08_plan_confirm_second_click_returns_duplicate() -> None:
    """A second plan_confirm click within the TTL window returns duplicate."""
    from app.tasks.card_tasks import _handle_plan_confirm

    graph = _make_graph_mock(state_values={"chat_id": DEMO_CHAT_ID})
    mock_resume = MagicMock()
    redis_mock_first = _make_redis_mock([True])
    redis_mock_second = _make_redis_mock([None])

    value = {"thread_id": "t-step8"}

    with (
        patch("app.graph.get_or_init_graph", new=AsyncMock(return_value=graph)),
        patch("app.tasks.card_tasks._send_progress_card", new=AsyncMock()),
        patch("app.tasks.message_tasks.resume_graph_task", mock_resume),
    ):
        with patch("redis.asyncio.from_url", return_value=redis_mock_first):
            r1 = await _handle_plan_confirm(value)
        with patch("redis.asyncio.from_url", return_value=redis_mock_second):
            r2 = await _handle_plan_confirm(value)

    assert r1["status"] == "dispatched"
    assert r2["status"] == "duplicate"
    mock_resume.delay.assert_called_once()


# ── Step 9 — 5 次并发点击只派发 1 次 ─────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step09_five_concurrent_plan_confirms_only_one_dispatched() -> None:
    """Five concurrent plan_confirm clicks produce exactly one dispatch."""
    from app.tasks.card_tasks import _handle_plan_confirm

    graph = _make_graph_mock(state_values={"chat_id": DEMO_CHAT_ID})
    mock_resume = MagicMock()

    # First caller wins the SETNX lock; all others see None (already locked)
    acquired_sequence = [True, None, None, None, None]

    redis_mock = _make_redis_mock(acquired_sequence)

    value = {"thread_id": "t-step9"}

    with (
        patch("redis.asyncio.from_url", return_value=redis_mock),
        patch("app.graph.get_or_init_graph", new=AsyncMock(return_value=graph)),
        patch("app.tasks.card_tasks._send_progress_card", new=AsyncMock()),
        patch("app.tasks.message_tasks.resume_graph_task", mock_resume),
    ):
        results = await asyncio.gather(*[_handle_plan_confirm(value) for _ in range(5)])

    dispatched = [r for r in results if r["status"] == "dispatched"]
    duplicate = [r for r in results if r["status"] == "duplicate"]
    assert len(dispatched) == 1
    assert len(duplicate) == 4
    mock_resume.delay.assert_called_once()


# ── Step 10 — 暂停 + 续跑 ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step10_pause_keyword_pauses_then_resume_continues(demo_plan) -> None:
    """Pause keyword sets pending_user_action; checkpoint_resume re-dispatches."""
    from app.graph.nodes.checkpoint_control import checkpoint_control_node
    from app.tasks.card_tasks import _handle_checkpoint_resume

    # Sub-step A: step_router routes to checkpoint_control when pending="pause"
    pause_state = _base_state(
        intent=IntentSchema(
            task_type=TaskType.create_new,
            primary_goal="Q3复盘",
            output_formats=[OutputFormat.document],
            ambiguity_score=0.0,
        ),
        plan=demo_plan,
        completed_steps=["context_retrieval", "doc_structure_gen"],
        pending_user_action="pause",
    )
    assert route(pause_state) == "checkpoint_control"

    # Sub-step B: checkpoint_control emits pause card and returns waiting_human
    node_state = _base_state(
        plan=demo_plan,
        completed_steps=["context_retrieval", "doc_structure_gen"],
    )
    mock_reply_card = AsyncMock()
    with patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter:
        MockAdapter.return_value = AsyncMock(reply_card=mock_reply_card)
        result = await checkpoint_control_node(node_state)

    assert result["status"] == TaskStatus.waiting_human
    assert result["pending_user_action"]["kind"] == "user_paused"

    # Sub-step C: checkpoint_resume re-dispatches graph continuation
    graph = _make_graph_mock(state_values={"chat_id": DEMO_CHAT_ID})
    mock_resume = MagicMock()
    with (
        patch("app.graph.get_or_init_graph", new=AsyncMock(return_value=graph)),
        patch("app.tasks.card_tasks._send_progress_card", new=AsyncMock()),
        patch("app.tasks.message_tasks.resume_graph_task", mock_resume),
    ):
        resume_result = await _handle_checkpoint_resume({"thread_id": "t-step10"})

    assert resume_result["status"] == "dispatched"
    mock_resume.delay.assert_called_once()


# ── Step 11 — 跨会话产物检索 ─────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step11_prior_artifact_retrieved_from_chromadb(
    demo_delivered_ppt_chunks,
) -> None:
    """prior_artifact_retrieval finds previously delivered PPT from ChromaDB."""
    from app.graph.nodes.prior_artifact_retrieval import prior_artifact_retrieval_node

    modify_intent = IntentSchema(
        task_type=TaskType.modify_existing,
        primary_goal="Q3复盘汇报",
        output_formats=[OutputFormat.presentation],
        ambiguity_score=0.2,
    )

    state = _base_state(
        normalized_text="上次给VP看的复盘材料，我想再调一下",
        intent=modify_intent,
        doc=None,
        ppt=None,
        completed_steps=[],
    )

    # step_router should route to prior_artifact_retrieval (no artifact in state)
    assert route(state) == "prior_artifact_retrieval"

    mock_query = AsyncMock(return_value=demo_delivered_ppt_chunks)
    mock_reply_card = AsyncMock()

    with (
        patch("app.services.chroma_service.ChromaService.query", new=mock_query),
        patch("app.integrations.feishu.adapter.FeishuAdapter.reply_card", new=mock_reply_card),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
    ):
        result = await prior_artifact_retrieval_node(state)

    assert "prior_artifact_retrieval" in result["completed_steps"]

    ppt = result["ppt"]
    assert ppt.ppt_id == "ppt_prev_001"
    assert len(ppt.slides) == 3
    assert ppt.slides[0].title == "封面"

    assert result["pending_user_action"]["kind"] == "confirm_prior_artifact"
    assert result["pending_user_action"]["ppt_id"] == "ppt_prev_001"

    mock_reply_card.assert_awaited()
    card_str = str(mock_reply_card.call_args_list)
    assert "confirm_prior_artifact" in card_str

    mock_query.assert_awaited_once()
    assert mock_query.call_args.kwargs.get("extra_where") == {"source": "delivered"}


# ── Step 12 — 故障降级 (LLM → Lite 模型) ─────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.demo_critical
async def test_step12_llm_error_triggers_lite_tier_downgrade() -> None:
    """First LLM error downgrades to Lite and retries; second error terminates."""
    from app.graph.nodes.error_handler import error_handler_node

    # First failure (retry_count=0): should downgrade to lite
    state1 = _base_state(
        error="LLMError: timeout — RateLimitExceeded",
        status=TaskStatus.failed,
        retry_count=0,
    )

    with (
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now") as mock_send,
    ):
        result1 = await error_handler_node(state1)

    assert result1["_force_tier"] == "lite"
    assert result1["status"] == TaskStatus.running
    assert result1["error"] is None
    assert result1["retry_count"] == 1
    assert result1.get("intent") is None

    # After downgrade, step_router sees intent=None → routes to intent_parser
    merged = {**state1, **result1}
    assert route(merged) == "intent_parser"

    # Check that Lite downgrade message was emitted via _send_now
    call_str = str(mock_send.call_args_list)
    assert "Lite" in call_str or "lite" in call_str or "降级" in call_str

    # Second failure (retry_count=1): standard termination path
    state2 = _base_state(
        error="LLMError: timeout — RateLimitExceeded",
        status=TaskStatus.failed,
        retry_count=1,
    )

    with (
        patch("app.services.progress_broadcaster.ProgressBroadcaster._emit"),
        patch("app.services.progress_broadcaster.ProgressBroadcaster._send_now"),
    ):
        result2 = await error_handler_node(state2)

    assert result2.get("_force_tier") is None
    assert result2["status"] == TaskStatus.completed
