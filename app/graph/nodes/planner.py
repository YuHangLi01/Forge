"""planner node: generate PlanSchema from intent + context, with 1 retry + template fallback."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.graph.nodes._validators import build_available_nodes_prompt, get_allowed_nodes
from app.schemas.plan import PlanSchema, PlanStep

logger = structlog.get_logger(__name__)

_TEMPLATE_PLAN = PlanSchema(
    steps=[
        PlanStep(id="step_1", node_name="doc_structure_gen", depends_on=[], estimated_seconds=10),
        PlanStep(
            id="step_2",
            node_name="doc_content_gen",
            depends_on=["step_1"],
            estimated_seconds=60,
        ),
        PlanStep(
            id="step_3",
            node_name="feishu_doc_write",
            depends_on=["step_2"],
            estimated_seconds=5,
        ),
    ],
    total_estimated_seconds=75,
)


def _validate_plan(plan: PlanSchema) -> bool:
    """Return True if the plan passes structural validation."""
    ids = {s.id for s in plan.steps}
    if not ids:
        return False

    # Node whitelist (stage-gated)
    from app.config import get_settings

    allowed = get_allowed_nodes(get_settings().FORGE_STAGE)
    for step in plan.steps:
        if step.node_name not in allowed:
            logger.warning("plan_invalid_node", node_name=step.node_name)
            return False

    # Dependency closure — all deps must exist
    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in ids:
                logger.warning("plan_missing_dep", step=step.id, dep=dep)
                return False

    # Cycle detection via DFS
    graph: dict[str, list[str]] = {s.id: s.depends_on for s in plan.steps}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _has_cycle(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for nb in graph.get(node, []):
            if nb not in visited and _has_cycle(nb):
                return True
            if nb in in_stack:
                return True
        in_stack.discard(node)
        return False

    if any(_has_cycle(s.id) for s in plan.steps if s.id not in visited):
        logger.warning("plan_cycle_detected")
        return False

    # Total time constraint
    if plan.total_estimated_seconds > 150:
        logger.warning("plan_too_long", total_seconds=plan.total_estimated_seconds)
        return False

    return True


@graph_node("planner")
async def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.planner  # noqa: F401  # registers PROMPT_V1
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    intent = state.get("intent")
    context: list[dict[str, Any]] = state.get("retrieved_context") or []

    primary_goal = getattr(intent, "primary_goal", "生成文档") if intent else "生成文档"
    task_type = str(getattr(intent, "task_type", "create_new")) if intent else "create_new"
    output_formats = (
        [str(f) for f in getattr(intent, "output_formats", ["document"])]
        if intent
        else ["document"]
    )

    context_summary = "\n".join(c.get("text", "")[:200] for c in context[:3]) or "（无背景资料）"

    prompt_version = get_prompt("planner")
    from app.config import get_settings

    available_nodes = build_available_nodes_prompt(get_settings().FORGE_STAGE)
    filled = prompt_version.text.format(
        primary_goal=primary_goal,
        task_type=task_type,
        output_formats=", ".join(output_formats),
        context_summary=context_summary,
        available_nodes=available_nodes,
    )

    llm = LLMService()
    plan: PlanSchema | None = None

    for attempt in range(2):
        try:
            candidate: PlanSchema = await llm.structured(filled, PlanSchema, tier="pro")
            if _validate_plan(candidate):
                plan = candidate
                break
            logger.warning("plan_validation_failed", attempt=attempt)
        except Exception:
            logger.exception("planner_llm_failed", attempt=attempt)

    if plan is None:
        logger.warning("planner_using_template_fallback")
        plan = _TEMPLATE_PLAN

    logger.info(
        "plan_generated",
        steps=[s.node_name for s in plan.steps],
        total_seconds=plan.total_estimated_seconds,
    )
    return {"plan": plan}
