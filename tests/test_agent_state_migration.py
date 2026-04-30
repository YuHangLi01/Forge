"""Tests for AgentState v2 evolution and migrate_v1_to_v2.

Verifies:
- v1 dicts (missing new fields) are promoted to v2 safely
- v2 dicts pass through unchanged
- state_from_checkpoint applies migration before deserializing Pydantic models
- modification_history round-trips through state_to_json / state_from_checkpoint
- ModificationRecord is frozen (immutable after creation)
"""

import json

import pytest

from app.schemas.agent_state import (
    make_agent_state,
    migrate_v1_to_v2,
    state_from_checkpoint,
    state_to_json,
)
from app.schemas.modification import ModificationRecord

# ---------------------------------------------------------------------------
# migrate_v1_to_v2
# ---------------------------------------------------------------------------


def test_v1_dict_gets_all_new_fields() -> None:
    v1 = {"task_id": "t1", "user_id": "u1", "chat_id": "c1", "message_id": "m1"}
    result = migrate_v1_to_v2(v1)
    assert result["schema_version"] == "v2"
    assert result["pending_user_action"] is None
    assert result["modification_history"] == []
    assert result["attachments"] == []
    assert result["completed_section_ids"] == []


def test_v2_dict_unchanged_by_migration() -> None:
    v2 = {
        "schema_version": "v2",
        "pending_user_action": {"kind": "clarify"},
        "modification_history": [
            {
                "step_index": 0,
                "scope_identifier": "x",
                "instruction": "y",
                "before_summary": "b",
                "after_summary": "a",
            }
        ],
        "attachments": [{"name": "f"}],
        "completed_section_ids": ["s1"],
    }
    result = migrate_v1_to_v2(v2)
    # Existing values must not be overwritten
    assert result["pending_user_action"] == {"kind": "clarify"}
    assert len(result["modification_history"]) == 1
    assert result["attachments"] == [{"name": "f"}]
    assert result["completed_section_ids"] == ["s1"]


def test_migration_is_idempotent() -> None:
    v1 = {"user_id": "u"}
    once = migrate_v1_to_v2(v1)
    twice = migrate_v1_to_v2(once)
    assert once == twice


def test_migration_does_not_mutate_original() -> None:
    original = {"task_id": "t1"}
    migrate_v1_to_v2(original)
    assert "schema_version" not in original


# ---------------------------------------------------------------------------
# make_agent_state — v2 by default
# ---------------------------------------------------------------------------


def test_make_agent_state_has_v2_fields() -> None:
    state = make_agent_state(user_id="u1", chat_id="c1", message_id="m1")
    assert state["schema_version"] == "v2"
    assert state["pending_user_action"] is None
    assert state["modification_history"] == []
    assert state["attachments"] == []
    assert state["completed_section_ids"] == []


# ---------------------------------------------------------------------------
# state_from_checkpoint — migration + Pydantic deserialisation
# ---------------------------------------------------------------------------


def test_state_from_checkpoint_upgrades_v1() -> None:
    from app.schemas.enums import TaskStatus

    checkpoint = {
        "task_id": "t1",
        "user_id": "u1",
        "chat_id": "c1",
        "message_id": "m1",
        "status": "pending",
    }
    state = state_from_checkpoint(checkpoint)
    assert state["schema_version"] == "v2"
    assert state["pending_user_action"] is None
    assert state["modification_history"] == []
    assert state["status"] == TaskStatus.pending


def test_state_from_checkpoint_deserialises_modification_records() -> None:
    checkpoint = {
        "modification_history": [
            {
                "step_index": 0,
                "scope_identifier": "第二节",
                "instruction": "简洁化",
                "before_summary": "原文很长",
                "after_summary": "精简后",
            }
        ]
    }
    state = state_from_checkpoint(checkpoint)
    assert len(state["modification_history"]) == 1
    rec = state["modification_history"][0]
    assert isinstance(rec, ModificationRecord)
    assert rec.scope_identifier == "第二节"


# ---------------------------------------------------------------------------
# state_to_json / round-trip
# ---------------------------------------------------------------------------


def test_modification_record_round_trips_json() -> None:
    rec = ModificationRecord(
        step_index=0,
        scope_identifier="第一节",
        instruction="扩写",
        before_summary="短",
        after_summary="长了很多",
    )
    state = make_agent_state(user_id="u", chat_id="c", message_id="m")
    state["modification_history"] = [rec]

    serialized = state_to_json(state)
    loaded = json.loads(serialized)
    assert loaded["modification_history"][0]["scope_identifier"] == "第一节"

    restored = state_from_checkpoint(loaded)
    assert isinstance(restored["modification_history"][0], ModificationRecord)
    assert restored["modification_history"][0].step_index == 0


# ---------------------------------------------------------------------------
# ModificationRecord immutability
# ---------------------------------------------------------------------------


def test_modification_record_is_frozen() -> None:
    rec = ModificationRecord(
        step_index=0,
        scope_identifier="x",
        instruction="y",
        before_summary="b",
        after_summary="a",
    )
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        rec.step_index = 99  # type: ignore[misc]
