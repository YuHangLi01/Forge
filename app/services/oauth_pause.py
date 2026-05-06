"""Redis-backed registry for graphs paused awaiting Feishu OAuth.

When intent_parser pauses on calendar auth, it writes (user_id → thread_id, chat_id)
here. The OAuth callback pops the entry and dispatches resume_graph_task on success.
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

_KEY_TMPL = "pending_oauth:{user_id}"
_TTL_SECONDS = 600  # 10 min — graph is abandoned if user never authorizes


async def mark_oauth_pending(user_id: str, thread_id: str, chat_id: str) -> None:
    settings = get_settings()
    async with aioredis.from_url(settings.REDIS_URL, decode_responses=True) as r:  # type: ignore[no-untyped-call]
        await r.setex(
            _KEY_TMPL.format(user_id=user_id),
            _TTL_SECONDS,
            json.dumps({"thread_id": thread_id, "chat_id": chat_id}),
        )
    logger.info("oauth_pause_marked", user_id=user_id, thread_id=thread_id)


async def pop_oauth_pending(user_id: str) -> dict[str, str] | None:
    settings = get_settings()
    async with aioredis.from_url(settings.REDIS_URL, decode_responses=True) as r:  # type: ignore[no-untyped-call]
        raw = await r.get(_KEY_TMPL.format(user_id=user_id))
        if raw is None:
            return None
        await r.delete(_KEY_TMPL.format(user_id=user_id))
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        logger.warning("oauth_pause_pop_decode_failed", user_id=user_id)
        return None
