from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas.artifacts import DocArtifact, PPTArtifact
from app.schemas.enums import TaskStatus
from app.schemas.intent import IntentSchema, ModificationIntent
from app.schemas.modification import ModificationRecord
from app.schemas.plan import PlanSchema


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

    # Outputs
    doc: DocArtifact | None
    ppt: PPTArtifact | None
    completed_section_ids: list[str]

    # PPT generation pipeline
    ppt_brief: dict[str, Any] | None  # output of ppt_structure_gen
    ppt_slides: list[dict[str, Any]]  # output of ppt_content_gen (per-slide content)
    completed_slide_ids: list[int]  # for breakpoint resume in ppt_content_gen

    # Modification history — each edit appended; capped at 50 in doc_section_editor
    modification_history: Annotated[list[ModificationRecord], operator.add]  # reducer: append-only

    # Human-in-the-loop: set by clarify_question, consumed + cleared by clarify_resume
    pending_user_action: dict[str, Any] | None

    # Lifecycle
    status: TaskStatus
    error: str | None
    retry_count: int
    schema_version: str
    created_at: str
    updated_at: str
