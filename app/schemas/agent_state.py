from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.schemas.artifacts import DocArtifact, PPTArtifact
from app.schemas.enums import TaskStatus
from app.schemas.intent import IntentSchema, ModificationIntent
from app.schemas.modification import ModificationRecord
from app.schemas.plan import PlanSchema


def _make_task_id() -> str:
    return f"task_{uuid4().hex[:12]}"


# AgentState is a plain dict (TypedDict protocol) for LangGraph compatibility.
# LangGraph StateGraph requires TypedDict, not Pydantic BaseModel, for channel reducers.
# We use a typed factory and helper functions instead of methods.

AgentState = dict[str, Any]


def make_agent_state(
    user_id: str,
    chat_id: str,
    message_id: str,
    task_id: str | None = None,
) -> AgentState:
    now = datetime.now(UTC)
    return {
        "schema_version": "v2",
        "task_id": task_id or _make_task_id(),
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "raw_input": "",
        "normalized_text": "",
        "attachments": [],
        "intent": None,
        "plan": None,
        "current_step": None,
        "completed_steps": [],
        "retrieved_context": [],
        "completed_section_ids": [],
        "doc": None,
        "ppt": None,
        "mod_intent": None,
        "modification_history": [],
        "pending_user_action": None,
        "status": TaskStatus.pending,
        "error": None,
        "retry_count": 0,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


_V2_DEFAULTS: dict[str, Any] = {
    "schema_version": "v2",
    "attachments": [],
    "completed_section_ids": [],
    "modification_history": [],
    "pending_user_action": None,
}


def migrate_v1_to_v2(d: dict[str, Any]) -> dict[str, Any]:
    """Idempotent migration: fill any missing v2 fields with safe defaults.

    Safe to run on already-v2 dicts; existing values are never overwritten.
    """
    out = dict(d)
    for key, default in _V2_DEFAULTS.items():
        if key not in out:
            out[key] = default
    return out


def add_completed_step(state: AgentState, step_id: str) -> AgentState:
    """Return a new state dict with step_id appended to completed_steps."""
    return {
        **state,
        "completed_steps": [*state["completed_steps"], step_id],
        "updated_at": datetime.now(UTC).isoformat(),
    }


def state_to_json(state: AgentState) -> str:
    """Serialize state to JSON for LangGraph checkpoint storage."""

    def _default(obj: Any) -> Any:
        _pydantic_types = (
            IntentSchema,
            ModificationIntent,
            ModificationRecord,
            PlanSchema,
            DocArtifact,
            PPTArtifact,
        )
        if isinstance(obj, _pydantic_types):
            return obj.model_dump()
        if isinstance(obj, TaskStatus):
            return obj.value
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(state, default=_default)


def state_from_checkpoint(d: dict[str, Any]) -> AgentState:
    """Deserialize state from LangGraph checkpoint dict.

    Always migrates to v2 first so in-flight v1 tasks gain the new fields
    without disrupting their in-progress work.
    """
    state = migrate_v1_to_v2(dict(d))
    if isinstance(state.get("intent"), dict):
        state["intent"] = IntentSchema.model_validate(state["intent"])
    if isinstance(state.get("plan"), dict):
        state["plan"] = PlanSchema.model_validate(state["plan"])
    if isinstance(state.get("doc"), dict):
        state["doc"] = DocArtifact.model_validate(state["doc"])
    if isinstance(state.get("ppt"), dict):
        state["ppt"] = PPTArtifact.model_validate(state["ppt"])
    if isinstance(state.get("mod_intent"), dict):
        state["mod_intent"] = ModificationIntent.model_validate(state["mod_intent"])
    if isinstance(state.get("status"), str):
        state["status"] = TaskStatus(state["status"])
    # Deserialize any already-serialized ModificationRecord dicts
    state["modification_history"] = [
        ModificationRecord.model_validate(r) if isinstance(r, dict) else r
        for r in state.get("modification_history", [])
    ]
    return state
