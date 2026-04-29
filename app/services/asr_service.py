"""Voice transcription service.

Backend defaults to Feishu native STT (`FeishuASRClient`). The Volc client
under `app.integrations.volc_asr` is kept as a deprecated fallback for now;
swap the constructor argument if Feishu STT becomes unavailable.
"""

import structlog

from app.integrations.feishu.adapter import FeishuAdapter
from app.integrations.feishu_asr.client import FeishuASRClient

logger = structlog.get_logger(__name__)


class ASRService:
    def __init__(
        self,
        feishu: FeishuAdapter,
        asr: FeishuASRClient | None = None,
    ) -> None:
        self._feishu = feishu
        self._asr = asr or FeishuASRClient()

    async def transcribe_voice_message(self, message_id: str, file_key: str) -> str:
        """Download a Feishu voice message and transcribe it.

        Returns the recognized text or an empty string on any failure (the
        caller — typically `handle_message_task` — substitutes a fallback
        prompt rather than crashing the worker).
        """
        try:
            audio_bytes = await self._feishu.download_message_resource(
                message_id, file_key, type_="audio"
            )
            text = await self._asr.transcribe(audio_bytes, audio_format="opus")
            logger.info("voice_transcribed", message_id=message_id, text_len=len(text))
            return text
        except Exception as exc:
            logger.warning("asr_failed", message_id=message_id, error=str(exc))
            return ""
