"""Temporary audio serving endpoint for Volcengine ASR v3.

Volcengine's recording-file transcription API requires an HTTPS URL to fetch
the audio. Forge stores the audio bytes in Redis (TTL 5 min) under
asr_audio:{token} and exposes them here so Volcengine can download them.
"""

from __future__ import annotations

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import get_settings

router = APIRouter()
logger = structlog.get_logger(__name__)

_AUDIO_KEY_PREFIX = "asr_audio:"


@router.get("/asr-audio/{token}", include_in_schema=False)
async def serve_asr_audio(token: str) -> Response:
    """Serve a temporary audio blob stored by VolcASRV3Client."""
    settings = get_settings()
    async with aioredis.from_url(settings.REDIS_URL) as r:  # type: ignore[no-untyped-call]
        data: bytes | None = await r.get(f"{_AUDIO_KEY_PREFIX}{token}")
    if not data:
        logger.warning("asr_audio_not_found", token=token)
        raise HTTPException(status_code=404, detail="Audio not found or expired")
    return Response(content=data, media_type="audio/ogg")
