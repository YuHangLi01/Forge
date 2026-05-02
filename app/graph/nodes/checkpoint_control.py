"""checkpoint_control: mid-execution pause/resume control node."""

from __future__ import annotations

from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node

logger = structlog.get_logger(__name__)

PAUSE_KEYWORDS: frozenset[str] = frozenset({"暂停", "等等", "停一下", "wait"})
RESUME_KEYWORDS: frozenset[str] = frozenset({"继续", "接着干", "resume"})
CANCEL_KEYWORDS: frozenset[str] = frozenset({"取消"})


def detect_control_intent(text: str) -> str | None:
    """Return 'pause', 'resume', 'cancel', or None.

    Exact-word match for pause keywords to avoid false positives (e.g. "等" alone
    does not trigger pause; only "等等" does).
    """
    stripped = text.strip()
    if any(kw in stripped for kw in PAUSE_KEYWORDS):
        return "pause"
    if any(kw in stripped for kw in RESUME_KEYWORDS):
        return "resume"
    if any(kw in stripped for kw in CANCEL_KEYWORDS):
        return "cancel"
    return None


@graph_node("checkpoint_control")
async def checkpoint_control_node(state: dict[str, Any]) -> dict[str, Any]:
    """Emits a pause card showing progress and suspends graph execution."""
    from app.graph.cards.pause_resume_card import build_pause_card
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.schemas.enums import TaskStatus

    message_id: str = state.get("message_id", "")
    completed_steps: list[str] = list(state.get("completed_steps") or [])
    plan = state.get("plan")

    pending_steps: list[str] = []
    if plan is not None:
        all_steps = [s.node_name for s in (plan.steps or [])]
        pending_steps = [s for s in all_steps if s not in completed_steps]

    card = build_pause_card(
        completed_steps=completed_steps,
        pending_steps=pending_steps,
        thread_id=message_id,
    )

    if message_id:
        try:
            await FeishuAdapter().reply_card(message_id, card)
        except Exception:
            logger.exception("pause_card_send_failed", message_id=message_id)

    logger.info(
        "execution_paused",
        message_id=message_id,
        completed=completed_steps,
        pending=pending_steps,
    )

    return {
        "status": TaskStatus.waiting_human,
        "_pause_reason": "user_paused",
        "pending_user_action": {"kind": "user_paused", "thread_id": message_id},
    }
