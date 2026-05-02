from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas.artifacts import DocArtifact, PPTArtifact
from app.schemas.enums import TaskStatus
from app.schemas.intent import IntentSchema, ModificationIntent
from app.schemas.modification import ModificationRecord
from app.schemas.plan import PlanSchema


def _capped_mod_history(a: list[Any], b: list[Any]) -> list[Any]:
    """Append-only reducer capped at 50 entries."""
    return (a + b)[-50:]


class AgentState(TypedDict, total=False):
    # Identity
    task_id: str
    user_id: str
    chat_id: str
    message_id: str

    # Input pipeline
    raw_input: str
    normalized_text: str
    attachments: list[dict[str, Any]]

    # Reasoning
    intent: IntentSchema | None
    plan: PlanSchema | None
    mod_intent: ModificationIntent | None

    # Execution tracking
    current_step: str | None
    completed_steps: Annotated[list[str], operator.add]  # reducer: append-only
    retrieved_context: list[dict[str, Any]]

    # Document generation pipeline
    doc_outline: dict[str, Any] | None  # produced by doc_structure_gen, consumed by doc_content_gen
    doc_markdown: str  # produced by doc_content_gen, consumed by feishu_doc_write

    # Outputs
    doc: DocArtifact | None
    ppt: PPTArtifact | None
    completed_section_ids: list[str]

    # PPT generation pipeline
    ppt_brief: dict[str, Any] | None  # output of ppt_structure_gen
    ppt_slides: list[dict[str, Any]]  # output of ppt_content_gen (per-slide content)
    completed_slide_ids: list[int]  # for breakpoint resume in ppt_content_gen

    # Modification history — capped reducer prevents unbounded growth
    modification_history: Annotated[list[ModificationRecord], _capped_mod_history]

    # Human-in-the-loop: clarify flow
    pending_user_action: dict[str, Any] | None
    clarify_answer: str | None  # injected by card_tasks when user submits the clarify card
    clarify_count: int  # how many clarify rounds have fired; guards against infinite loops

    # Lego multi-scenario orchestration
    _lego_scenarios: list[str] | None  # e.g. ["C", "D"]; set by scenario_composer

    # Checkpoint / pause-resume (S3-T07)
    _pause_reason: str | None  # "plan_confirm" | "user_paused"

    # Lifecycle
    status: TaskStatus
    error: str | None
    retry_count: int
    schema_version: str
    created_at: str
    updated_at: str
