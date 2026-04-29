import structlog

from app.integrations.feishu.adapter import FeishuAdapter
from app.integrations.volc_asr.client import VolcASRClient

logger = structlog.get_logger(__name__)


class ASRService:
    def __init__(self, feishu: FeishuAdapter, asr: VolcASRClient) -> None:
        self._feishu = feishu
        self._asr = asr

    async def transcribe_voice_message(self, message_id: str, file_key: str) -> str:
        """Download Feishu voice message and transcribe via ASR. Returns empty string on failure."""
        try:
            audio_bytes = await self._feishu.download_message_resource(
                message_id, file_key, type_="audio"
            )
            text = await self._asr.transcribe(audio_bytes, audio_format="amr")
            logger.info("voice_transcribed", message_id=message_id, text_len=len(text))
            return text
        except Exception as exc:
            logger.warning("asr_failed", message_id=message_id, error=str(exc))
            return ""
