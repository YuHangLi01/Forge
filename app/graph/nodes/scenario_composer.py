"""scenario_composer node: map intent.output_formats to lego scenario codes."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node

logger = structlog.get_logger(__name__)


@graph_node("scenario_composer")
async def scenario_composer_node(state: dict[str, Any]) -> dict[str, Any]:
    intent = state.get("intent")
    output_formats: list[str] = (
        [str(f) for f in getattr(intent, "output_formats", [])] if intent else []
    )

    scenarios: list[str] = []
    if "document" in output_formats:
        scenarios.append("C")
    if "presentation" in output_formats:
        scenarios.append("D")

    logger.info("scenario_composer_done", scenarios=scenarios, output_formats=output_formats)
    return {"_lego_scenarios": scenarios}
