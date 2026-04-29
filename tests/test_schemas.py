import json

import pytest
from pydantic import ValidationError

from app.schemas.agent_state import (
    add_completed_step,
    make_agent_state,
    state_from_checkpoint,
    state_to_json,
)
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
from app.schemas.plan import PlanSchema, PlanStep

# ---- IntentSchema -----------------------------------------------------------


def test_intent_schema_happy_path() -> None:
    intent = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="制作 Q3 复盘 PPT",
        output_formats=[OutputFormat.presentation],
        ambiguity_score=0.2,
    )
    assert intent.task_type == TaskType.create_new
    assert intent.ambiguity_score == 0.2
    assert intent.missing_info == []


def test_intent_schema_all_fields() -> None:
    intent = IntentSchema(
        task_type=TaskType.modify_existing,
        primary_goal="修改第三页标题",
        output_formats=[OutputFormat.presentation, OutputFormat.document],
        target_audience="管理层",
        style_hint="简洁",
        ambiguity_score=0.5,
        missing_info=["目标受众未明确"],
    )
    assert intent.target_audience == "管理层"
    assert len(intent.output_formats) == 2


def test_intent_schema_ambiguity_score_too_high() -> None:
    with pytest.raises(ValidationError):
        IntentSchema(
            task_type=TaskType.create_new,
            primary_goal="test",
            output_formats=[OutputFormat.document],
            ambiguity_score=1.5,
        )


def test_intent_schema_ambiguity_score_negative() -> None:
    with pytest.raises(ValidationError):
        IntentSchema(
            task_type=TaskType.create_new,
            primary_goal="test",
            output_formats=[OutputFormat.document],
            ambiguity_score=-0.1,
        )


def test_intent_schema_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentSchema(  # type: ignore[call-arg]
            task_type=TaskType.create_new,
            primary_goal="test",
            output_formats=[],
            ambiguity_score=0.0,
            unknown_field="oops",
        )


# ---- ModificationIntent -----------------------------------------------------


def test_modification_intent_happy_path() -> None:
    mod = ModificationIntent(
        target=OutputFormat.presentation,
        scope_type=ScopeType.specific_slide,
        scope_identifier="第三页",
        modification_type=ModificationType.rewrite,
        instruction="把标题改为'市场分析'",
    )
    assert mod.scope_identifier == "第三页"
    assert mod.modification_type == ModificationType.rewrite


# ---- PlanStep & PlanSchema --------------------------------------------------


def test_plan_step_defaults() -> None:
    step = PlanStep(id="step_1", node_name="intent_parser")
    assert step.depends_on == []
    assert step.requires_human_confirm is False
    assert step.estimated_seconds == 30


def test_plan_schema_next_runnable_step_first() -> None:
    plan = PlanSchema(
        steps=[
            PlanStep(id="s1", node_name="parse_intent"),
            PlanStep(id="s2", node_name="rag", depends_on=["s1"]),
            PlanStep(id="s3", node_name="write_doc", depends_on=["s2"]),
        ],
        total_estimated_seconds=90,
    )
    step = plan.next_runnable_step(completed=set())
    assert step is not None
    assert step.id == "s1"


def test_plan_schema_next_runnable_step_with_completed() -> None:
    plan = PlanSchema(
        steps=[
            PlanStep(id="s1", node_name="parse_intent"),
            PlanStep(id="s2", node_name="rag", depends_on=["s1"]),
        ],
        total_estimated_seconds=60,
    )
    step = plan.next_runnable_step(completed={"s1"})
    assert step is not None
    assert step.id == "s2"


def test_plan_schema_next_runnable_step_all_done() -> None:
    plan = PlanSchema(
        steps=[PlanStep(id="s1", node_name="parse_intent")],
        total_estimated_seconds=30,
    )
    step = plan.next_runnable_step(completed={"s1"})
    assert step is None


# ---- DocArtifact & PPTArtifact ----------------------------------------------


def test_doc_artifact_happy_path() -> None:
    doc = DocArtifact(
        doc_id="doxcnXXXXXXX",
        title="Q3 复盘报告",
        sections=[
            DocSection(id="sec_1", title="背景", content_md="## 背景\n...", block_ids=["blk_1"])
        ],
        share_url="https://example.feishu.cn/docx/xxx",
    )
    assert doc.doc_id == "doxcnXXXXXXX"
    assert len(doc.sections) == 1
    assert doc.sections[0].block_ids == ["blk_1"]


def test_doc_artifact_empty_sections() -> None:
    doc = DocArtifact(doc_id="doxcn123", title="Empty")
    assert doc.sections == []
    assert doc.share_url == ""


def test_ppt_artifact_happy_path() -> None:
    ppt = PPTArtifact(
        ppt_id="ppt_token_xxx",
        title="Q3 PPT",
        slides=[
            SlideSchema(
                page_index=0,
                layout=SlideLayout.cover,
                title="封面",
                bullets=[],
                speaker_notes="开场白",
            )
        ],
    )
    assert len(ppt.slides) == 1
    assert ppt.slides[0].layout == SlideLayout.cover


def test_slide_schema_defaults() -> None:
    slide = SlideSchema(page_index=1, title="第一页")
    assert slide.bullets == []
    assert slide.speaker_notes == ""
    assert slide.element_ids == {}


# ---- AgentState helpers -----------------------------------------------------


def test_make_agent_state_defaults() -> None:
    state = make_agent_state(user_id="u1", chat_id="c1", message_id="m1")
    assert state["user_id"] == "u1"
    assert state["status"] == TaskStatus.pending
    assert state["completed_steps"] == []
    assert state["task_id"].startswith("task_")


def test_make_agent_state_custom_task_id() -> None:
    state = make_agent_state(user_id="u1", chat_id="c1", message_id="m1", task_id="task_custom")
    assert state["task_id"] == "task_custom"


def test_add_completed_step() -> None:
    state = make_agent_state(user_id="u1", chat_id="c1", message_id="m1")
    state2 = add_completed_step(state, "step_1")
    assert "step_1" in state2["completed_steps"]
    # Original unchanged (new dict)
    assert state["completed_steps"] == []


def test_state_to_json_round_trip() -> None:
    state = make_agent_state(user_id="u1", chat_id="c1", message_id="m1")
    state["intent"] = IntentSchema(
        task_type=TaskType.create_new,
        primary_goal="test",
        output_formats=[OutputFormat.document],
        ambiguity_score=0.1,
    )
    state["doc"] = DocArtifact(doc_id="doc1", title="Test")
    state["ppt"] = PPTArtifact(ppt_id="ppt1", title="Test PPT")
    state["plan"] = PlanSchema(
        steps=[PlanStep(id="s1", node_name="parse")],
        total_estimated_seconds=30,
    )

    serialized = state_to_json(state)
    parsed = json.loads(serialized)
    assert parsed["user_id"] == "u1"
    assert parsed["intent"]["task_type"] == "create_new"
    assert parsed["doc"]["doc_id"] == "doc1"


def test_state_from_checkpoint_restores_types() -> None:
    state = make_agent_state(user_id="u2", chat_id="c2", message_id="m2")
    state["intent"] = IntentSchema(
        task_type=TaskType.query_only,
        primary_goal="query",
        output_formats=[OutputFormat.message_only],
        ambiguity_score=0.0,
    )
    state["status"] = TaskStatus.running

    # Simulate round-trip through JSON (like checkpoint storage)
    raw = json.loads(state_to_json(state))
    restored = state_from_checkpoint(raw)

    assert isinstance(restored["intent"], IntentSchema)
    assert restored["intent"].task_type == TaskType.query_only
    assert restored["status"] == TaskStatus.running


def test_state_json_serializable() -> None:
    """LangGraph compatibility: state dict must be JSON serializable."""
    state = make_agent_state(user_id="u3", chat_id="c3", message_id="m3")
    serialized = state_to_json(state)
    parsed = json.loads(serialized)
    assert parsed["retry_count"] == 0


# ---- Enums ------------------------------------------------------------------


def test_enums_are_str_serializable() -> None:
    assert json.dumps(TaskStatus.pending) == '"pending"'
    assert json.dumps(OutputFormat.document) == '"document"'
    assert json.dumps(TaskType.create_new) == '"create_new"'
