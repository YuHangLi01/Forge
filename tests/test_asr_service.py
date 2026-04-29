"""Unit tests for ASRService.

Uses AsyncMock for both FeishuAdapter and FeishuASRClient so the test
doesn't need real Feishu / network. The service's contract: download
audio → transcribe → return text; on any exception, swallow and return
empty string (so the caller sees a degraded prompt rather than a crash).
"""

from unittest.mock import AsyncMock

import pytest

from app.exceptions import ASRError
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
    asr.transcribe.assert_awaited_once_with(b"audio-bytes", audio_format="opus")


@pytest.mark.asyncio
async def test_transcribe_voice_message_returns_empty_on_download_failure() -> None:
    feishu = AsyncMock()
    feishu.download_message_resource.side_effect = RuntimeError("download boom")
    asr = AsyncMock()

    service = ASRService(feishu=feishu, asr=asr)
    result = await service.transcribe_voice_message("om_msg_2", "fk_2")

    assert result == ""
    asr.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_transcribe_voice_message_returns_empty_on_asr_error() -> None:
    feishu = AsyncMock()
    feishu.download_message_resource.return_value = b"audio"
    asr = AsyncMock()
    asr.transcribe.side_effect = ASRError("feishu_stt code=99991671")

    service = ASRService(feishu=feishu, asr=asr)
    result = await service.transcribe_voice_message("om_msg_3", "fk_3")

    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_voice_message_empty_text_returned_as_is() -> None:
    """ASR succeeds but recognises no speech → ASRService returns "" (not error)."""
    feishu = AsyncMock()
    feishu.download_message_resource.return_value = b"silence"
    asr = AsyncMock()
    asr.transcribe.return_value = ""

    service = ASRService(feishu=feishu, asr=asr)
    result = await service.transcribe_voice_message("om_msg_4", "fk_4")

    assert result == ""
    asr.transcribe.assert_awaited_once()
