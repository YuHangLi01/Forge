"""step_router: central routing node that decides the next graph node after each work step.

Priority order:
  1. Terminal state override — cancelled/failed → error_handler immediately.
  2. Human-in-the-loop gate — pending_user_action set → END (graph pauses).
  3. Modification path — task_type==modify_existing: route through
     mod_intent_parser then doc_section_editor.
  4. Plan-driven path — in order:
     a. No intent yet → intent_parser
     b. Intent ambiguous (score > 0.7) → clarify_question
     c. Context not yet retrieved → context_retrieval
     d. No plan → planner
     e. Plan has next runnable step → that step's node_name
     f. All steps done → END
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END

from app.schemas.enums import TaskStatus, TaskType


def route(state: dict[str, Any]) -> str:
    """Pure routing function — no side effects, no I/O.

    Returns a node name (str) or END sentinel so LangGraph can route correctly.
    """
    status = state.get("status")

    # ── Priority 1: terminal states ──────────────────────────────────────────
    if status in (TaskStatus.cancelled, TaskStatus.failed):
        return "error_handler"

    # Completed is also terminal — prevents modify-path or plan-path from looping.
    if status == TaskStatus.completed:
        return END

    # ── Priority 2: waiting for human response ───────────────────────────────
    pending = state.get("pending_user_action")
    if pending == "pause":
        return "checkpoint_control"
    if pending:
        return END

    # ── Priority 2.5: clarify answer received — merge it via clarify_resume ──
    if state.get("clarify_answer"):
        return "clarify_resume"

    intent = state.get("intent")

    # ── Priority 3: modification path ────────────────────────────────────────
    if intent is not None and getattr(intent, "task_type", None) == TaskType.modify_existing:
        if state.get("mod_intent") is None:
            return "mod_intent_parser"
        return "doc_section_editor"

    # ── Priority 4a: no intent yet ───────────────────────────────────────────
    if intent is None:
        return "intent_parser"

    # ── Priority 4b: intent too ambiguous (max 2 clarify rounds) ────────────
    if getattr(intent, "ambiguity_score", 0.0) > 0.7 and (state.get("clarify_count") or 0) < 2:
        return "clarify_question"

    completed = set(state.get("completed_steps") or [])

    # ── Priority 4c: context not retrieved yet ───────────────────────────────
    if "context_retrieval" not in completed:
        return "context_retrieval"

    # ── Priority 4d: plan not built yet ─────────────────────────────────────
    plan = state.get("plan")
    if plan is None:
        # Multi-format requests (doc + ppt) are handled by the lego path.
        output_formats = list(getattr(intent, "output_formats", []))
        has_doc = any(str(f) == "document" for f in output_formats)
        has_ppt = any(str(f) == "presentation" for f in output_formats)
        if has_doc and has_ppt:
            if not state.get("_lego_scenarios"):
                return "scenario_composer"
            return "lego_orchestrator"
        return "planner"

    # ── Priority 4e/f: follow the plan ──────────────────────────────────────
    next_step = plan.next_runnable_step(completed)
    if next_step is None:
        return END  # END sentinel is str-compatible at runtime
    return str(next_step.node_name)


async def step_router_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node wrapper — routing lives in route() so tests can call it directly."""
    return {}
