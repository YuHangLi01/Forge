"""ProgressBroadcaster: throttled progress card updates during graph execution.

Rate limit: at most one update_card call per second per message_id.
Throttle mechanism: Redis SETNX with EX 1. If the lock is already held,
the payload is written to `progress_pending:{message_id}` (overwriting
any prior unsent payload).  A Celery beat task (`flush_pending_progress`,
scheduled every 2 s in fast queue) drains the pending keys and sends
one final card update per message_id.

Idempotency for first-card creation:
  progress_card:{message_id} is set to "pending" (SETNX) before the async
  reply_card call fires.  Any concurrent _send_update that sees "pending"
  parks its payload in progress_pending instead of calling reply_card again.
  Once reply_card returns the real card message_id it overwrites "pending".

All Redis I/O uses redis.asyncio so it never blocks the event loop.
Sync callers (begin_node / end_node) schedule async work via create_task
when an event loop is running, or asyncio.run() otherwise.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_THROTTLE_KEY = "progress_throttle:{message_id}"
_PENDING_KEY = "progress_pending:{message_id}"
_CARD_ID_KEY = "progress_card:{message_id}"
_THROTTLE_TTL = 1  # seconds
_CARD_ID_TTL = 1800  # 30 minutes
_CARD_CREATING_TTL = 30  # seconds — max time to wait for first reply_card to complete


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

    def emit_clarify(self, questions: list[str], request_id: str) -> None:  # noqa: ARG002
        from app.graph.cards.templates import clarify_card

        card = clarify_card(questions=questions)
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
        """Throttled emit: run async Redis work in an isolated daemon thread.

        create_task() is intentionally NOT used here.  Celery workers run each
        task on a short-lived asyncio event loop (via run_sync); tasks scheduled
        with create_task are destroyed when that loop closes before they run,
        producing "Task was destroyed but it is pending!" warnings and no actual
        card update.  Running in a daemon thread gives _emit_async its own loop
        via asyncio.run(), which is independent of the calling loop's lifecycle.
        """
        card = dict(self._current_card)  # snapshot before any mutation
        threading.Thread(
            target=asyncio.run,
            args=(self._emit_async(card),),
            daemon=True,
        ).start()

    async def _emit_async(self, card: dict[str, Any]) -> None:
        """Async core of _emit: acquire throttle lock then update or park."""
        import redis.asyncio as aioredis

        try:
            from app.config import get_settings

            settings = get_settings()
            throttle_key = _THROTTLE_KEY.format(message_id=self.message_id)
            pending_key = _PENDING_KEY.format(message_id=self.message_id)

            async with aioredis.from_url(settings.REDIS_URL) as r:  # type: ignore[no-untyped-call]
                acquired = await r.set(throttle_key, "1", nx=True, ex=_THROTTLE_TTL)
                if acquired:
                    await self._send_update_async(r, card)
                else:
                    # Park for flush task
                    await r.set(pending_key, json.dumps(card), ex=10)
        except Exception:
            logger.exception("progress_broadcaster_emit_failed", message_id=self.message_id)

    async def _send_update_async(self, r: Any, card: dict[str, Any]) -> None:
        """Create or update the running progress card via Feishu API."""
        from app.integrations.feishu.adapter import FeishuAdapter

        card_key = _CARD_ID_KEY.format(message_id=self.message_id)
        pending_key = _PENDING_KEY.format(message_id=self.message_id)

        # Atomically claim "first sender" by setting card_key = "pending" (NX).
        is_first = await r.set(card_key, "pending", nx=True, ex=_CARD_CREATING_TTL)
        adapter = FeishuAdapter()
        if is_first:
            new_id = await adapter.reply_card(self.message_id, card)
            if new_id:
                await r.set(card_key, new_id, ex=_CARD_ID_TTL)
            else:
                await r.delete(card_key)
            return

        raw = await r.get(card_key)
        card_message_id: str | None = (
            (raw.decode() if isinstance(raw, bytes) else raw) if raw else None
        )

        if not card_message_id or card_message_id == "pending":
            # First card still being created; park for flush.
            await r.set(pending_key, json.dumps(card), ex=10)
            return

        await adapter.update_card(card_message_id, card)

    def _send_now(self, card: dict[str, Any]) -> None:
        """Reply to user's original message with a brand-new card (for emit_* calls).

        Uses the same daemon-thread pattern as _emit() so the send is not subject
        to the calling event loop's lifecycle (critical in Celery workers).
        """
        message_id = self.message_id

        def _run() -> None:
            try:
                from app.integrations.feishu.adapter import FeishuAdapter

                asyncio.run(FeishuAdapter().reply_card(message_id, card))
            except Exception:
                logger.exception("progress_broadcaster_send_failed", message_id=message_id)

        threading.Thread(target=_run, daemon=True).start()

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
