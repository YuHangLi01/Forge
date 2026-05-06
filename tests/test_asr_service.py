"""Unit tests for ASRService (Volcengine ASR v3 backend).

Uses AsyncMock for FeishuAdapter and VolcASRV3Client so no real network calls.
Contract: download audio → transcribe → return text; on any exception, raise
ForgeError so the caller (preprocess_node → error_handler) gets the real cause.
"""

from unittest.mock import AsyncMock

import pytest

from app.exceptions import ASRError, ForgeError
from app.services.asr_service import ASRService


@pytest.mark.asyncio
async def test_transcribe_voice_message_pipeline() -> None:
    feishu = AsyncMock()
    feishu.download_message_resource.return_value = b"audio-bytes"
    asr = AsyncMock()
    asr.transcribe.return_value = "你好"

    service = ASRService(feishu=feishu, asr=asr)
    result = await service.transcribe_voice_message("om_msg_1", "fk_1")

    assert result == "你好"
    feishu.download_message_resource.assert_awaited_once_with("om_msg_1", "fk_1", type_="audio")
    # Feishu opus voice messages → ogg format for Volcengine v3
    asr.transcribe.assert_awaited_once_with(b"audio-bytes", audio_format="ogg")


@pytest.mark.asyncio
async def test_transcribe_voice_message_raises_forge_error_on_download_failure() -> None:
    feishu = AsyncMock()
    feishu.download_message_resource.side_effect = RuntimeError("download boom")
    asr = AsyncMock()

    service = ASRService(feishu=feishu, asr=asr)
    with pytest.raises(ForgeError, match="语音转写失败"):
        await service.transcribe_voice_message("om_msg_2", "fk_2")
    asr.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_voice_message_raises_forge_error_on_asr_error() -> None:
    feishu = AsyncMock()
    feishu.download_message_resource.return_value = b"audio"
    asr = AsyncMock()
    asr.transcribe.side_effect = ASRError("volc_asr_v3 error: code=45000001")

    service = ASRService(feishu=feishu, asr=asr)
    with pytest.raises(ForgeError, match="语音转写失败"):
        await service.transcribe_voice_message("om_msg_3", "fk_3")


@pytest.mark.asyncio
async def test_transcribe_voice_message_empty_text_returned_as_is() -> None:
    """ASR succeeds but recognises no speech → ASRService returns "" (caller raises)."""
    feishu = AsyncMock()
    feishu.download_message_resource.return_value = b"silence"
    asr = AsyncMock()
    asr.transcribe.return_value = ""

    service = ASRService(feishu=feishu, asr=asr)
    result = await service.transcribe_voice_message("om_msg_4", "fk_4")

    assert result == ""
    asr.transcribe.assert_awaited_once()
