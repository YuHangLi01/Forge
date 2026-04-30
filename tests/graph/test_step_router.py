"""Tests for step_router.route() — the central graph routing function.

Covers all 12+ branches listed in the S2-T05 routing table.
route() is tested as a pure function; no graph compilation required.
"""

from unittest.mock import MagicMock

from langgraph.graph import END

from app.graph.nodes.step_router import route
from app.schemas.enums import TaskStatus, TaskType

# ── helpers ──────────────────────────────────────────────────────────────────


def _intent(task_type: TaskType = TaskType.create_new, ambiguity: float = 0.0) -> MagicMock:
    m = MagicMock()
    m.task_type = task_type
    m.ambiguity_score = ambiguity
    return m


def _plan(next_node: str | None) -> MagicMock:
    step = MagicMock()
    step.node_name = next_node
    p = MagicMock()
    p.next_runnable_step.return_value = step if next_node else None
    return p


# ── Priority 1: terminal states ───────────────────────────────────────────────


def test_cancelled_goes_to_error_handler() -> None:
    state = {"status": TaskStatus.cancelled}
    assert route(state) == "error_handler"


def test_failed_goes_to_error_handler() -> None:
    state = {"status": TaskStatus.failed}
    assert route(state) == "error_handler"


# ── Priority 2: human-in-the-loop ────────────────────────────────────────────


def test_pending_user_action_pauses_graph() -> None:
    state = {"pending_user_action": {"kind": "clarify", "request_id": "abc"}}
    assert route(state) == END


def test_pending_user_action_ignored_when_cancelled() -> None:
    """Priority 1 beats Priority 2."""
    state = {"status": TaskStatus.cancelled, "pending_user_action": {"kind": "clarify"}}
    assert route(state) == "error_handler"


# ── Priority 3: modification path ────────────────────────────────────────────


def test_modify_intent_without_mod_intent_goes_to_mod_intent_parser() -> None:
    state = {"intent": _intent(TaskType.modify_existing), "mod_intent": None}
    assert route(state) == "mod_intent_parser"


def test_modify_intent_with_mod_intent_goes_to_doc_section_editor() -> None:
    state = {
        "intent": _intent(TaskType.modify_existing),
        "mod_intent": MagicMock(),
    }
    assert route(state) == "doc_section_editor"


# ── Priority 4a: no intent yet ───────────────────────────────────────────────


def test_no_intent_goes_to_intent_parser() -> None:
    state: dict = {}
    assert route(state) == "intent_parser"


def test_none_intent_goes_to_intent_parser() -> None:
    state = {"intent": None}
    assert route(state) == "intent_parser"


# ── Priority 4b: ambiguous intent ────────────────────────────────────────────


def test_high_ambiguity_goes_to_clarify_question() -> None:
    state = {"intent": _intent(ambiguity=0.8)}
    assert route(state) == "clarify_question"


def test_borderline_ambiguity_not_clarified() -> None:
    """ambiguity_score == 0.7 is NOT above the threshold."""
    state = {
        "intent": _intent(ambiguity=0.7),
        "completed_steps": ["context_retrieval"],
        "plan": _plan("doc_structure_gen"),
    }
    assert route(state) == "doc_structure_gen"


# ── Priority 4c: context retrieval ───────────────────────────────────────────


def test_context_not_retrieved_yet_goes_to_retrieval() -> None:
    state = {"intent": _intent(ambiguity=0.2), "completed_steps": []}
    assert route(state) == "context_retrieval"


def test_context_already_retrieved_skips_retrieval() -> None:
    state = {
        "intent": _intent(ambiguity=0.2),
        "completed_steps": ["context_retrieval"],
        "plan": None,
    }
    assert route(state) == "planner"


# ── Priority 4d: planner ─────────────────────────────────────────────────────


def test_no_plan_goes_to_planner() -> None:
    state = {
        "intent": _intent(),
        "completed_steps": ["context_retrieval"],
        "plan": None,
    }
    assert route(state) == "planner"


# ── Priority 4e/f: plan-driven ───────────────────────────────────────────────


def test_plan_drives_next_node() -> None:
    state = {
        "intent": _intent(),
        "completed_steps": ["context_retrieval"],
        "plan": _plan("doc_structure_gen"),
    }
    assert route(state) == "doc_structure_gen"


def test_all_plan_steps_complete_returns_end() -> None:
    state = {
        "intent": _intent(),
        "completed_steps": ["context_retrieval"],
        "plan": _plan(None),  # next_runnable_step returns None
    }
    assert route(state) == END


# ── Scenario: cancel during waiting ──────────────────────────────────────────


def test_cancel_during_clarify_wait() -> None:
    """User cancels while graph is paused for clarification."""
    state = {
        "status": TaskStatus.cancelled,
        "pending_user_action": {"kind": "clarify", "request_id": "x"},
    }
    assert route(state) == "error_handler"
