import base64

import httpx
import structlog

from app.config import get_settings
from app.exceptions import ASRError

logger = structlog.get_logger(__name__)

_ASR_URL = "https://openspeech.bytedance.com/api/v1/asr"
_TIMEOUT = 8.0


class VolcASRClient:
    """Volcano Engine one-shot ASR client for short audio (≤60s)."""

    def __init__(self) -> None:
        settings = get_settings()
        self._app_id = settings.VOLC_ASR_APP_ID
        self._access_token = settings.VOLC_ASR_ACCESS_TOKEN
        self._cluster = settings.VOLC_ASR_CLUSTER

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str = "amr",
        sample_rate: int = 16000,
        language: str = "zh-CN",
    ) -> str:
        """Transcribe audio bytes to text via Volcano Engine ASR API."""
        audio_b64 = base64.b64encode(audio_bytes).decode()
        payload = {
            "app": {
                "appid": self._app_id,
                "cluster": self._cluster,
                "token": self._access_token,
            },
            "user": {"uid": "forge"},
            "request": {
                "reqid": "forge_asr",
                "sequence": 1,
                "nbest": 1,
                "show_utterances": False,
            },
            "audio": {
                "format": audio_format,
                "rate": sample_rate,
                "language": language,
                "bits": 16,
                "channel": 1,
                "codec": "raw",
                "data": audio_b64,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    _ASR_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer; {self._access_token}"},
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("code") != 1000:
                    code, msg = data.get("code"), data.get("message")
                    raise ASRError(f"ASR API error: code={code} msg={msg}")

                utterances = data.get("utterances", [])
                if not utterances:
                    return ""
                text: str = utterances[0].get("text", "")
                logger.info("asr_transcribed", chars=len(text))
                return text

        except ASRError:
            raise
        except Exception as exc:
            raise ASRError(f"ASR request failed: {exc}") from exc
