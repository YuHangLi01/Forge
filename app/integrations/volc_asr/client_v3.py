"""Volcengine recording-file transcription client (API v3).

Two-stage async flow:
  1. POST /api/v3/auc/bigmodel/submit  — submit audio URL, get task queued
  2. POST /api/v3/auc/bigmodel/query   — poll with same X-Api-Request-Id until done

Auth uses legacy-console headers (X-Api-App-Key / X-Api-Access-Key).
Audio is stored in Redis for 5 minutes under asr_audio:{token} and served via
Forge's own /api/v1/asr-audio/{token} endpoint so Volcengine can fetch it.

Ref: https://www.volcengine.com/docs/6561/1354868
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import structlog

from app.config import get_settings
from app.exceptions import ASRError

logger = structlog.get_logger(__name__)

_SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
_QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
_AUDIO_KEY_PREFIX = "asr_audio:"
_AUDIO_TTL_SEC = 300
_POLL_INTERVAL_SEC = 2.0
_MAX_POLLS = 30

_CODE_SUCCESS = 20000000
_CODE_PROCESSING = 20000001
_CODE_QUEUED = 20000002


class VolcASRV3Client:
    """Volcengine ASR v3 recording-file transcription client."""

    def __init__(self) -> None:
        settings = get_settings()
        self._app_key = settings.VOLC_ASR_APP_ID
        self._access_key = settings.VOLC_ASR_ACCESS_TOKEN
        self._resource_id = settings.VOLC_ASR_RESOURCE_ID
        self._public_url = settings.FORGE_PUBLIC_URL.rstrip("/")
        self._redis_url = settings.REDIS_URL

    def _headers(self, request_id: str) -> dict[str, str]:
        return {
            "X-Api-App-Key": self._app_key,
            "X-Api-Access-Key": self._access_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1",
            "Content-Type": "application/json",
        }

    async def _store_audio(self, audio_bytes: bytes) -> str:
        """Store bytes in Redis and return the token (URL suffix)."""
        import redis.asyncio as aioredis

        token = uuid.uuid4().hex
        async with aioredis.from_url(self._redis_url) as r:  # type: ignore[no-untyped-call]
            await r.set(f"{_AUDIO_KEY_PREFIX}{token}", audio_bytes, ex=_AUDIO_TTL_SEC)
        return token

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "ogg",
        language: str = "zh-CN",
    ) -> str:
        """Upload audio to Redis, submit to Volcengine, poll until done.

        audio_format: format string accepted by Volcengine (raw|wav|mp3|ogg).
        Feishu opus voice messages are wrapped in an OGG container → use "ogg".
        """
        if not self._public_url:
            raise ASRError(
                "FORGE_PUBLIC_URL is not configured — "
                "Volcengine ASR v3 needs a publicly accessible URL to fetch audio"
            )
        token = await self._store_audio(audio_bytes)
        audio_url = f"{self._public_url}/api/v1/asr-audio/{token}"
        request_id = str(uuid.uuid4())
        headers = self._headers(request_id)

        payload: dict[str, Any] = {
            "audio": {
                "url": audio_url,
                "format": audio_format,
                "channel": 1,
            },
            "request": {
                "enable_itn": True,
                "enable_punc": True,
                "language": language,
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            # ── Submit ────────────────────────────────────────────────────────
            resp = await client.post(_SUBMIT_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                raise ASRError(f"volc_asr_v3 submit http {resp.status_code}: {resp.text[:200]}")
            data: dict[str, Any] = resp.json()
            code = data.get("code")
            if code not in (_CODE_PROCESSING, _CODE_QUEUED):
                raise ASRError(
                    f"volc_asr_v3 submit rejected: code={code} msg={data.get('message')}"
                )
            logger.info("volc_asr_v3_submitted", request_id=request_id, audio_url=audio_url)

            # ── Poll ──────────────────────────────────────────────────────────
            for attempt in range(1, _MAX_POLLS + 1):
                await asyncio.sleep(_POLL_INTERVAL_SEC)
                resp = await client.post(_QUERY_URL, json={}, headers=headers)
                if resp.status_code != 200:
                    raise ASRError(f"volc_asr_v3 query http {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                code = data.get("code")
                if code == _CODE_SUCCESS:
                    result: dict[str, Any] = data.get("result") or {}
                    text: str = result.get("text", "")
                    logger.info(
                        "volc_asr_v3_done",
                        request_id=request_id,
                        chars=len(text),
                        polls=attempt,
                    )
                    return text
                if code in (_CODE_PROCESSING, _CODE_QUEUED):
                    continue
                raise ASRError(f"volc_asr_v3 error: code={code} msg={data.get('message')}")

        raise ASRError(f"volc_asr_v3 polling timeout after {_MAX_POLLS * _POLL_INTERVAL_SEC:.0f}s")
