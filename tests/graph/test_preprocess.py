"""Tests for the preprocess node — 4 input branches + edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import ForgeError
from app.graph.nodes.preprocess import preprocess_node

# ── Branch 1: plain text ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_text_message_sets_normalized_text() -> None:
    state = {"raw_input": "  帮我写一份会议纪要  ", "attachments": []}
    result = await preprocess_node(state)
    assert result["normalized_text"] == "帮我写一份会议纪要"


@pytest.mark.asyncio
async def test_text_message_no_attachments_key() -> None:
    state = {"raw_input": "hello"}
    result = await preprocess_node(state)
    assert result["normalized_text"] == "hello"


@pytest.mark.asyncio
async def test_empty_text_raises_forge_error() -> None:
    state = {"raw_input": "   ", "attachments": []}
    with pytest.raises(ForgeError):
        await preprocess_node(state)


@pytest.mark.asyncio
async def test_missing_raw_input_raises_forge_error() -> None:
    state: dict = {}
    with pytest.raises(ForgeError):
        await preprocess_node(state)


# ── Branch 2: audio → ASR ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audio_attachment_calls_asr() -> None:
    state = {
        "raw_input": "",
        "message_id": "msg-001",
        "attachments": [{"type": "audio", "file_key": "fk-abc", "message_id": "msg-001"}],
    }
    mock_asr = AsyncMock(return_value="这是转写后的文字")
    # Patch at source — imports happen lazily inside the function body
    with (
        patch("app.integrations.feishu.adapter.FeishuAdapter"),
        patch("app.services.asr_service.ASRService") as MockASR,
    ):
        MockASR.return_value.transcribe_voice_message = mock_asr
        result = await preprocess_node(state)

    assert result["normalized_text"] == "这是转写后的文字"
    mock_asr.assert_awaited_once_with("msg-001", "fk-abc")


@pytest.mark.asyncio
async def test_audio_asr_empty_result_raises_forge_error() -> None:
    state = {
        "raw_input": "",
        "message_id": "msg-002",
        "attachments": [{"type": "audio", "file_key": "fk-xyz", "message_id": "msg-002"}],
    }
    with (
        patch("app.integrations.feishu.adapter.FeishuAdapter"),
        patch("app.services.asr_service.ASRService") as MockASR,
    ):
        MockASR.return_value.transcribe_voice_message = AsyncMock(return_value="")
        with pytest.raises(ForgeError, match="empty transcript"):
            await preprocess_node(state)


# ── Branch 3: file → text extraction ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_attachment_extracts_text() -> None:
    txt_content = b"Meeting notes: item 1\nitem 2\n"
    state = {
        "raw_input": "",
        "message_id": "msg-003",
        "attachments": [{"type": "file", "file_key": "fk-doc", "file_name": "notes.txt"}],
    }
    mock_feishu = MagicMock()
    mock_feishu.download_message_resource = AsyncMock(return_value=txt_content)
    with (
        patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_feishu),
        patch("app.services.file_extractor.extract_text_from_file") as mock_extract,
    ):
        mock_extract.return_value = "Meeting notes: item 1\nitem 2"
        result = await preprocess_node(state)

    assert result["normalized_text"] == "Meeting notes: item 1\nitem 2"


@pytest.mark.asyncio
async def test_file_too_large_raises_forge_error() -> None:
    large_content = b"x" * (11 * 1024 * 1024)  # 11 MB
    state = {
        "raw_input": "",
        "message_id": "msg-004",
        "attachments": [{"type": "file", "file_key": "fk-big", "file_name": "big.txt"}],
    }
    mock_feishu = MagicMock()
    mock_feishu.download_message_resource = AsyncMock(return_value=large_content)
    with (
        patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_feishu),
        patch(
            "app.services.file_extractor.extract_text_from_file",
            side_effect=ForgeError("File too large", code=413),
        ),
        pytest.raises(ForgeError, match="too large"),
    ):
        await preprocess_node(state)


# ── Unsupported attachment type ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_attachment_type_raises_forge_error() -> None:
    state = {
        "raw_input": "",
        "attachments": [{"type": "image", "file_key": "fk-img"}],
    }
    with pytest.raises(ForgeError, match="Unsupported attachment type"):
        await preprocess_node(state)


# ── Race protection (from @graph_node decorator) ──────────────────────────────


@pytest.mark.asyncio
async def test_preprocess_skipped_when_pending_user_action() -> None:
    state = {
        "raw_input": "hello",
        "pending_user_action": {"kind": "clarify", "request_id": "r1"},
    }
    # @graph_node("preprocess") should return {} without calling the function body
    result = await preprocess_node(state)
    assert result == {}
