"""lego_orchestrator node: expand lego scenario codes into a serial PlanSchema.

Each scenario code maps to a fixed node chain. Scenarios are chained strictly
in order (no fan-out): the first step of scenario N depends on the last step
of scenario N-1. step_router then drives execution by following plan.next_runnable_step.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.enums import TaskStatus
from app.schemas.plan import PlanSchema, PlanStep
from app.services.progress_broadcaster import ProgressBroadcaster

logger = structlog.get_logger(__name__)

# Each scenario is a list of (id_suffix, node_name, estimated_seconds).
_SCENARIO_STEPS: dict[str, list[tuple[str, str, int]]] = {
    "C": [
        ("1", "doc_structure_gen", 15),
        ("2", "doc_content_gen", 60),
        ("3", "feishu_doc_write", 15),
    ],
    "D": [
        ("1", "ppt_structure_gen", 15),
        ("2", "ppt_content_gen", 60),
        ("3", "feishu_ppt_write", 30),
    ],
}


def compose_plan(lego_scenarios: list[str]) -> PlanSchema:
    """Build a topologically ordered, strictly serial PlanSchema.

    C → D example:
      C1(doc_structure_gen, []) → C2(doc_content_gen,[C1]) → C3(feishu_doc_write,[C2])
      → D1(ppt_structure_gen,[C3]) → D2(ppt_content_gen,[D1]) → D3(feishu_ppt_write,[D2])
    """
    steps: list[PlanStep] = []
    prev_last_id: str | None = None
    total_secs = 0

    for code in lego_scenarios:
        template = _SCENARIO_STEPS.get(code, [])
        for i, (suffix, node_name, est) in enumerate(template):
            step_id = f"{code}{suffix}"
            if i == 0 and prev_last_id is not None:
                depends: list[str] = [prev_last_id]
            elif i > 0:
                prev_suffix = template[i - 1][0]
                depends = [f"{code}{prev_suffix}"]
            else:
                depends = []

            steps.append(
                PlanStep(
                    id=step_id,
                    node_name=node_name,
                    depends_on=depends,
                    estimated_seconds=est,
                )
            )
            total_secs += est

        if template:
            prev_last_id = f"{code}{template[-1][0]}"

    return PlanSchema(steps=steps, total_estimated_seconds=total_secs)


@graph_node("lego_orchestrator")
async def lego_orchestrator_node(state: dict[str, Any]) -> dict[str, Any]:
    message_id = state.get("message_id", "")
    scenarios: list[str] = state.get("_lego_scenarios") or []
    if not scenarios:
        logger.warning("lego_orchestrator_no_scenarios")
        return {}

    plan = compose_plan(scenarios)
    logger.info(
        "lego_orchestrator_done",
        scenarios=scenarios,
        step_count=len(plan.steps),
        total_seconds=plan.total_estimated_seconds,
    )

    steps_preview = [
        {"node_name": s.node_name, "estimated_seconds": s.estimated_seconds} for s in plan.steps
    ]
    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    pb.emit_plan_preview(steps=steps_preview, total_seconds=plan.total_estimated_seconds)

    pending_action = {
        "kind": "plan_confirm",
        "thread_id": message_id,
    }
    return {
        "plan": plan,
        "pending_user_action": pending_action,
        "status": TaskStatus.waiting_human,
    }
