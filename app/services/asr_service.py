"""Voice transcription service.

Uses Volcengine recording-file transcription API v3 (VolcASRV3Client) as the
default backend. The legacy FeishuASRClient is kept in
app/integrations/feishu_asr/ as a fallback if needed.
"""

import structlog

from app.exceptions import ForgeError
from app.integrations.feishu.adapter import FeishuAdapter
from app.integrations.volc_asr.client_v3 import VolcASRV3Client

logger = structlog.get_logger(__name__)


class ASRService:
    def __init__(
        self,
        feishu: FeishuAdapter,
        asr: VolcASRV3Client | None = None,
    ) -> None:
        self._feishu = feishu
        self._asr = asr or VolcASRV3Client()

    async def transcribe_voice_message(self, message_id: str, file_key: str) -> str:
        """Download a Feishu voice message and transcribe it via Volcengine ASR v3.

        Returns the recognized text (may be empty if no speech detected).
        Raises ForgeError on download or ASR failures so the error propagates
        to error_handler with the real cause.
        """
        try:
            # Feishu audio resources have file_v3_ keys — the API type is "file", not "audio"
            audio_bytes = await self._feishu.download_message_resource(
                message_id, file_key, type_="file"
            )
            # Feishu voice messages use opus codec in an OGG container
            text = await self._asr.transcribe(audio_bytes, audio_format="ogg")
            logger.info("voice_transcribed", message_id=message_id, text_len=len(text))
            return text
        except Exception as exc:
            logger.warning("asr_failed", message_id=message_id, error=str(exc))
            raise ForgeError(f"语音转写失败（{exc}），请重试或改用文字输入", code=500) from exc
