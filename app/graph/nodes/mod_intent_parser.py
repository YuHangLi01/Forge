"""mod_intent_parser node: parse modification instruction with cross-product disambiguation."""

from __future__ import annotations

import re
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

_DOC_KEYWORDS_RE = re.compile(r"文档|节|章节|正文")
_PPT_KEYWORDS_RE = re.compile(r"PPT|ppt|幻灯片|页|slide|演示文稿")
_AMBIGUOUS_RE = re.compile(r"第\d+个|那个|刚才的|那个")


def _keyword_disambiguate(text: str) -> str | None:
    """Return 'document', 'presentation', or None (ambiguous)."""
    has_doc = bool(_DOC_KEYWORDS_RE.search(text))
    has_ppt = bool(_PPT_KEYWORDS_RE.search(text))
    if has_doc and not has_ppt:
        return "document"
    if has_ppt and not has_doc:
        return "presentation"
    return None


@graph_node("mod_intent_parser")
async def mod_intent_parser_node(state: dict[str, Any]) -> dict[str, Any]:
    import app.prompts.mod_intent_parser  # noqa: F401
    from app.prompts._versioning import get as get_prompt
    from app.services.llm_service import LLMService

    message_id: str = state.get("message_id", "")
    normalized_text: str = state.get("normalized_text", "")
    doc = state.get("doc")
    ppt = state.get("ppt")
    modification_history: list[Any] = state.get("modification_history") or []

    has_doc = doc is not None
    has_ppt = ppt is not None

    # Build doc structure summary
    doc_structure = "（无文档信息）"
    if has_doc:
        titles = [s.title for s in getattr(doc, "sections", [])]
        if titles:
            doc_structure = "\n".join(f"- {t}" for t in titles)

    # Build ppt structure summary
    ppt_structure = "（无 PPT 信息）"
    if has_ppt:
        slides = getattr(ppt, "slides", [])
        if slides:
            ppt_structure = "\n".join(f"- 第{s.page_index + 1}页: {s.title}" for s in slides[:10])

    # Include last 5 modification records
    recent_history = modification_history[-5:]
    if recent_history:
        history_lines = [
            f"- [{getattr(rec, 'scope_identifier', '?')}] {getattr(rec, 'instruction', '?')}"
            for rec in recent_history
        ]
        history_text = "\n".join(history_lines)
    else:
        history_text = "（暂无修改历史）"

    # Choose prompt version and pre-disambiguate when both artifacts exist
    force_target: str | None = None
    if has_doc and has_ppt:
        # Keyword-based pre-disambiguation (highest priority)
        force_target = _keyword_disambiguate(normalized_text)

        # History-based fallback: if still ambiguous, use last target
        if force_target is None and recent_history:
            last_rec = recent_history[-1]
            last_target = str(getattr(last_rec, "target", "document"))
            if last_target in ("document", "presentation"):
                force_target = last_target
                logger.debug("mod_target_inferred_from_history", target=force_target)

        from app.prompts.mod_intent_parser import PROMPT_V2

        filled = PROMPT_V2.text.format(
            user_instruction=normalized_text,
            doc_structure=doc_structure,
            ppt_structure=ppt_structure,
            modification_history=history_text,
        )
    else:
        prompt_version = get_prompt("mod_intent_parser")
        filled = prompt_version.text.format(
            user_instruction=normalized_text,
            doc_structure=doc_structure,
            modification_history=history_text,
        )
        if has_doc and not has_ppt:
            force_target = "document"
        elif has_ppt and not has_doc:
            force_target = "presentation"

    llm = LLMService()
    try:
        mod_intent: ModificationIntent = await llm.structured(
            filled, ModificationIntent, tier="pro"
        )
    except Exception:
        logger.exception("mod_intent_parser_failed")
        mod_intent = _FALLBACK

    # Override target when pre-disambiguation is conclusive
    if force_target is not None:
        mod_intent = ModificationIntent(
            target=force_target,  # type: ignore[arg-type]
            scope_type=mod_intent.scope_type,
            scope_identifier=mod_intent.scope_identifier,
            modification_type=mod_intent.modification_type,
            instruction=mod_intent.instruction,
            ambiguity_high=False,
        )

    logger.info(
        "mod_intent_parsed",
        target=mod_intent.target,
        scope_type=mod_intent.scope_type,
        scope_identifier=mod_intent.scope_identifier,
        ambiguity_high=mod_intent.ambiguity_high,
        has_doc=has_doc,
        has_ppt=has_ppt,
    )

    # Emit clarify card when target is genuinely ambiguous
    if mod_intent.ambiguity_high and has_doc and has_ppt:
        from app.graph.cards.templates import mod_target_clarify_card
        from app.integrations.feishu.adapter import FeishuAdapter

        card = mod_target_clarify_card(
            scope_identifier=mod_intent.scope_identifier,
            thread_id=message_id,
        )
        if message_id:
            try:
                await FeishuAdapter().reply_card(message_id, card)
            except Exception:
                logger.exception("mod_clarify_card_failed", message_id=message_id)

        return {
            "pending_user_action": {
                "kind": "mod_target_clarify",
                "thread_id": message_id,
                "scope_identifier": mod_intent.scope_identifier,
                "scope_type": str(mod_intent.scope_type),
                "modification_type": str(mod_intent.modification_type),
                "instruction": mod_intent.instruction,
            }
        }

    return {"mod_intent": mod_intent}
