"""Feishu native speech-to-text client.

Wraps `/open-apis/speech_to_text/v1/speech/file_recognize`. Used as the
default backend for `ASRService` in Stage 1; keeps Volc as a fallback
implementation under `app/integrations/volc_asr/` for now.
"""

import asyncio
import base64
import time
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.exceptions import ASRError

logger = structlog.get_logger(__name__)

_DEFAULT_DOMAIN = "https://open.feishu.cn"
_TOKEN_PATH = "/open-apis/auth/v3/tenant_access_token/internal"
_STT_PATH = "/open-apis/speech_to_text/v1/speech/file_recognize"
_HTTP_TIMEOUT = 10.0
_TOKEN_REFRESH_LEEWAY_SEC = 300.0


class FeishuASRClient:
    """Feishu native one-shot speech-to-text.

    The client caches a `tenant_access_token` and refreshes it ~5 min before
    expiry. Each `transcribe()` call POSTs the audio (base64-encoded) to
    Feishu's STT endpoint and returns the recognized text. Failures raise
    `ASRError`; callers (typically `ASRService`) decide whether to surface
    the error or degrade gracefully.
    """

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        domain: str | None = None,
    ) -> None:
        settings = get_settings()
        self._app_id = app_id or settings.FEISHU_APP_ID
        self._app_secret = app_secret or settings.FEISHU_APP_SECRET
        self._domain = (domain or settings.FEISHU_DOMAIN or _DEFAULT_DOMAIN).rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_tenant_access_token(self) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if self._token and now < self._token_expires_at - _TOKEN_REFRESH_LEEWAY_SEC:
                return self._token

            url = f"{self._domain}{_TOKEN_PATH}"
            payload = {"app_id": self._app_id, "app_secret": self._app_secret}
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise ASRError(f"tenant_access_token http {resp.status_code}: {resp.text[:200]}")
            data: dict[str, Any] = resp.json()
            if data.get("code") != 0:
                raise ASRError(f"tenant_access_token code={data.get('code')} msg={data.get('msg')}")
            token = data.get("tenant_access_token")
            if not isinstance(token, str) or not token:
                raise ASRError("tenant_access_token missing in response")
            expire = int(data.get("expire", 7200))
            self._token = token
            self._token_expires_at = now + expire
            return token

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "opus",
    ) -> str:
        """Transcribe audio bytes to text via Feishu STT.

        Returns the recognized text (may be empty if Feishu detected no speech).
        Raises ASRError on auth, network, or API-level failure (after retries).
        """
        if not audio_bytes:
            raise ASRError("audio_bytes is empty")

        token = await self._get_tenant_access_token()
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        payload = {
            "speech": {"speech": audio_b64},
            "config": {
                "file_id": "forge",
                "format": audio_format,
                "engine_type": "16k_auto",
            },
        }
        url = f"{self._domain}{_STT_PATH}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError, ASRError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 500:
                    resp.raise_for_status()
                if resp.status_code != 200:
                    raise ASRError(f"feishu_stt http {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                code = data.get("code")
                if code != 0:
                    raise ASRError(f"feishu_stt code={code} msg={data.get('msg', '')}")
                payload_data: dict[str, Any] = data.get("data", {}) or {}
                recognition_text: str = payload_data.get("recognition_text", "") or ""
                logger.info(
                    "feishu_stt_ok",
                    chars=len(recognition_text),
                    audio_format=audio_format,
                )
                return recognition_text

        raise ASRError("feishu_stt: retries exhausted")
