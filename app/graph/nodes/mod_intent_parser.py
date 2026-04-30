"""mod_intent_parser node: parse modification instruction (Pro LLM + history context)."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.intent import ModificationIntent

logger = structlog.get_logger(__name__)

_FALLBACK = ModificationIntent(
    target="document",
    scope_type="full",
    scope_identifier="全文",
    modification_type="rewrite",
    instruction="修改指令解析失败，请重新描述",
)


@graph_node("mod_intent_parser")
async def mod_intent_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.mod_intent_parser  # noqa: F401
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    normalized_text: str = state.get("normalized_text", "")
    doc = state.get("doc")
    modification_history: list[Any] = state.get("modification_history") or []

    # Build doc structure summary
    doc_structure = "（无文档信息）"
    if doc is not None:
        titles = [s.title for s in getattr(doc, "sections", [])]
        if titles:
            doc_structure = "\n".join(f"- {t}" for t in titles)

    # Include last 5 modification records for context
    recent_history = modification_history[-5:]
    if recent_history:
        history_lines = []
        for rec in recent_history:
            scope = getattr(rec, "scope_identifier", "?")
            instr = getattr(rec, "instruction", "?")
            history_lines.append(f"- [{scope}] {instr}")
        history_text = "\n".join(history_lines)
    else:
        history_text = "（暂无修改历史）"

    prompt_version = get_prompt("mod_intent_parser")
    filled = prompt_version.text.format(
        user_instruction=normalized_text,
        doc_structure=doc_structure,
        modification_history=history_text,
    )

    llm = LLMService()
    try:
        mod_intent: ModificationIntent = await llm.structured(
            filled, ModificationIntent, tier="pro"
        )
    except Exception:
        logger.exception("mod_intent_parser_failed")
        mod_intent = _FALLBACK

    logger.info(
        "mod_intent_parsed",
        scope_type=mod_intent.scope_type,
        scope_identifier=mod_intent.scope_identifier,
        modification_type=mod_intent.modification_type,
    )
    return {"mod_intent": mod_intent}
