"""ProgressBroadcaster: throttled progress card updates during graph execution.

Rate limit: at most one update_card call per second per message_id.
Throttle mechanism: Redis SETNX with EX 1. If the lock is already held,
the payload is written to `progress_pending:{message_id}` (overwriting
any prior unsent payload).  A Celery beat task (`flush_pending_progress`,
scheduled every 200 ms in fast queue) drains the pending keys and sends
one final card update per message_id.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis
import structlog

logger = structlog.get_logger(__name__)

_THROTTLE_KEY = "progress_throttle:{message_id}"
_PENDING_KEY = "progress_pending:{message_id}"
_THROTTLE_TTL = 1  # seconds


class ProgressBroadcaster:
    """Send throttled progress updates to a Feishu card.

    Parameters
    ----------
    message_id:
        The Feishu message_id of the card to update.
    thread_id:
        LangGraph thread_id (used for context, not sent to Feishu).
    """

    def __init__(self, message_id: str, thread_id: str) -> None:
        self.message_id = message_id
        self.thread_id = thread_id
        self._current_card: dict[str, Any] = {}

    # ── public API ────────────────────────────────────────────────────────────

    def begin_node(self, node_name: str) -> None:
        self._current_card = self._build_progress_card(f"⏳ 正在执行：{node_name}…")
        self._emit()

    def end_node(self, node_name: str) -> None:
        self._current_card = self._build_progress_card(f"✅ 已完成：{node_name}")
        self._emit()

    def update_thinking(self, text: str) -> None:
        from app.services.react_filter import sanitize

        safe = sanitize(text)
        if not safe:
            return
        self._current_card = self._build_progress_card(safe)
        self._emit()

    def emit_artifact(self, label: str, url: str) -> None:
        from app.graph.cards.templates import doc_done_card

        card = doc_done_card(label=label, url=url)
        self._send_now(card)

    def emit_clarify(self, questions: list[str], request_id: str) -> None:
        from app.graph.cards.templates import clarify_card

        card = clarify_card(questions=questions, request_id=request_id, thread_id=self.thread_id)
        self._send_now(card)

    def emit_plan_preview(self, steps: list[dict[str, Any]], total_seconds: int) -> None:
        from app.graph.cards.templates import plan_preview_card

        card = plan_preview_card(steps=steps, thread_id=self.thread_id, total_seconds=total_seconds)
        self._send_now(card)

    def emit_error(self, message: str) -> None:
        from app.graph.cards.templates import error_card

        self._send_now(error_card(message=message))

    # ── internal helpers ──────────────────────────────────────────────────────

    def _emit(self) -> None:
        """Throttled emit: send now if under rate limit, else queue for flush."""
        try:
            from app.config import get_settings

            settings = get_settings()
            r = redis.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]
            throttle_key = _THROTTLE_KEY.format(message_id=self.message_id)
            pending_key = _PENDING_KEY.format(message_id=self.message_id)

            acquired = r.set(throttle_key, "1", nx=True, ex=_THROTTLE_TTL)
            if acquired:
                self._send_now(self._current_card)
            else:
                # Park for flush task
                r.set(pending_key, json.dumps(self._current_card), ex=10)
        except Exception:
            logger.exception("progress_broadcaster_emit_failed", message_id=self.message_id)

    def _send_now(self, card: dict[str, Any]) -> None:
        try:
            from app.integrations.feishu.adapter import FeishuAdapter

            adapter = FeishuAdapter()
            asyncio.run(adapter.update_card(self.message_id, card))
        except Exception:
            logger.exception("progress_broadcaster_send_failed", message_id=self.message_id)

    @staticmethod
    def _build_progress_card(text: str) -> dict[str, Any]:
        return {
            "type": "card",
            "body": {"elements": [{"tag": "div", "text": {"content": text, "tag": "lark_md"}}]},
            "header": {
                "title": {"content": "Forge 正在处理…", "tag": "plain_text"},
                "template": "blue",
            },
        }


def flush_pending_for_message(message_id: str) -> bool:
    """Flush any parked payload for *message_id*. Returns True if something was sent."""
    try:
        from app.config import get_settings

        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL)  # type: ignore[no-untyped-call]
        pending_key = _PENDING_KEY.format(message_id=message_id)
        raw = r.getdel(pending_key)
        if raw is None:
            return False
        card = json.loads(raw)
        from app.integrations.feishu.adapter import FeishuAdapter

        adapter = FeishuAdapter()
        asyncio.run(adapter.update_card(message_id, card))
        return True
    except Exception:
        logger.exception("flush_pending_failed", message_id=message_id)
        return False
