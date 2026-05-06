"""Shared fixtures for the 12-step DEMO scenario tests.

All external dependencies (LLM, Feishu, ChromaDB, Redis) are mocked.
The _patch_env autouse fixture from tests/e2e/conftest.py is inherited
automatically by pytest for all tests in this subdirectory.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graph.builder import build_graph
from app.schemas.artifacts import DocArtifact, DocSection, PPTArtifact, SlideSchema
from app.schemas.enums import OutputFormat, TaskStatus, TaskType
from app.schemas.intent import IntentSchema
from app.schemas.plan import PlanSchema, PlanStep

# ── Demo identity constants ───────────────────────────────────────────────────

DEMO_USER_ID = "demo_zhangwei"
DEMO_MSG_ID = "om_demo_20260505"
DEMO_CHAT_ID = "oc_demo_group_01"
DEMO_TASK_ID = "task-demo-001"

# ── Shared fixture data ───────────────────────────────────────────────────────


@pytest.fixture()
def demo_calendar_events() -> list[dict]:
    return [
        {
            "summary": "VP 一对一",
            "start": "2026-05-05T14:00:00",
            "end": "2026-05-05T15:00:00",
        },
        {
            "summary": "团队评审",
            "start": "2026-05-05T16:00:00",
            "end": "2026-05-05T17:00:00",
        },
    ]


@pytest.fixture()
def demo_rag_results() -> list[dict]:
    return [
        {
            "text": "李娜: Q3整体跌了12%，主要发生在7月中旬，DAU单日最低跌至历史谷值。",
            "metadata": {"sender_user_id": "lina_001", "source": "chat"},
            "distance": 0.10,
        },
        {
            "text": "陈磊: v3.2.1时间线讨论，版本延期3周，直接影响DAU峰值，建议复盘。",
            "metadata": {"sender_user_id": "chenlei_002", "source": "chat"},
            "distance": 0.15,
        },
        {
            "text": "王芳: DAU与留存数据，7月留存率同比下降8pp，8月有所回升。",
            "metadata": {"sender_user_id": "wangfang_003", "source": "chat"},
            "distance": 0.20,
        },
    ]


@pytest.fixture()
def demo_intent() -> IntentSchema:
    return IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="Q3复盘汇报材料，给VP汇报",
        output_formats=[OutputFormat.document, OutputFormat.presentation],
        target_audience="VP",
        style_hint="corporate",
        ambiguity_score=0.3,
        missing_info=[],
    )


@pytest.fixture()
def demo_plan() -> PlanSchema:
    # delivery_node is NOT a plan step — step_router routes there automatically
    # when all plan steps complete (for create_new tasks).
    return PlanSchema(
        steps=[
            PlanStep(id="s1", node_name="doc_structure_gen", depends_on=[], estimated_seconds=5),
            PlanStep(id="s2", node_name="doc_content_gen", depends_on=["s1"], estimated_seconds=30),
            PlanStep(
                id="s3", node_name="feishu_doc_write", depends_on=["s2"], estimated_seconds=10
            ),
            PlanStep(id="s4", node_name="ppt_structure_gen", depends_on=[], estimated_seconds=5),
            PlanStep(id="s5", node_name="ppt_content_gen", depends_on=["s4"], estimated_seconds=60),
            PlanStep(
                id="s6", node_name="feishu_ppt_write", depends_on=["s5"], estimated_seconds=10
            ),
        ],
        total_estimated_seconds=120,
    )


@pytest.fixture()
def demo_doc_artifact() -> DocArtifact:
    sections = [
        DocSection(id=f"sec{i}", title=t, content_md=f"{t}的详细内容...")
        for i, t in enumerate(["Q3总结", "主要问题", "行动计划", "下季度展望"])
    ]
    return DocArtifact(
        doc_id="doc_demo_001",
        title="Q3复盘汇报",
        sections=sections,
        share_url="https://feishu.cn/doc/Q3demo",
    )


@pytest.fixture()
def demo_ppt_artifact() -> PPTArtifact:
    slides = [
        SlideSchema(
            page_index=i,
            title=f"第{i + 1}页",
            bullets=[f"要点{i}A", f"要点{i}B"],
        )
        for i in range(7)
    ]
    return PPTArtifact(
        ppt_id="ppt_demo_001",
        title="Q3复盘汇报",
        slides=slides,
        share_url="https://feishu.cn/ppt/Q3demo",
    )


@pytest.fixture()
def demo_delivered_ppt_chunks() -> list[dict]:
    """ChromaDB results for a previously delivered PPT (source=delivered)."""
    base_meta = {
        "source": "delivered",
        "chunk_type": "ppt_slide",
        "ppt_id": "ppt_prev_001",
        "ppt_title": "Q3复盘汇报",
        "share_url": "https://feishu.cn/ppt/Q3demo",
        "task_id": "task-prev-001",
    }
    return [
        {
            "text": "Q3复盘汇报 第1页：封面\n• Q3复盘",
            "metadata": {**base_meta, "slide_index": 0, "slide_title": "封面"},
            "distance": 0.05,
        },
        {
            "text": "Q3复盘汇报 第2页：业绩总结\n• DAU -12%\n• 7月中旬下滑",
            "metadata": {**base_meta, "slide_index": 1, "slide_title": "业绩总结"},
            "distance": 0.08,
        },
        {
            "text": "Q3复盘汇报 第3页：问题分析\n• 竞品冲击\n• 功能迭代延迟",
            "metadata": {**base_meta, "slide_index": 2, "slide_title": "问题分析"},
            "distance": 0.12,
        },
    ]


@pytest.fixture()
def memory_graph():
    """Compiled graph with MemorySaver — no external checkpointer deps."""
    return build_graph(MemorySaver())


# ── State helper ──────────────────────────────────────────────────────────────


def _base_state(**extra) -> dict:
    """Minimum-valid AgentState dict for demo scenario tests."""
    return {
        "task_id": DEMO_TASK_ID,
        "user_id": DEMO_USER_ID,
        "chat_id": DEMO_CHAT_ID,
        "message_id": DEMO_MSG_ID,
        "raw_input": "帮我准备明天的VP一对一复盘材料",
        "normalized_text": "帮我准备明天的VP一对一复盘材料",
        "status": TaskStatus.running,
        **extra,
    }
