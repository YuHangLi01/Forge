"""preprocess node: normalize the incoming Feishu message into state.normalized_text.

Input shape (from initial state built in message_tasks):
  - state["raw_input"]: raw text content (empty string for audio/file messages)
  - state["attachments"]: list of attachment dicts; each has "type", "file_key",
      optionally "file_name" and "message_id"
  - state["message_id"]: Feishu message_id (used by ASR download)

Branches:
  1. No attachments + non-empty raw_input → text message → pass through
  2. Attachment type "audio" → download + ASR → normalized_text
  3. Attachment type "file" → download + file_extractor → normalized_text
  4. Empty text after processing → ForgeError (caught by error_handler)

Size limit: >10 MB files are rejected by file_extractor (ForgeError 413).
"""

from __future__ import annotations

from typing import Any

import structlog

from app.exceptions import ForgeError
from app.graph.nodes._decorator import graph_node

logger = structlog.get_logger(__name__)

_MAX_AUDIO_BYTES = 20 * 1024 * 1024  # 20 MB — Feishu voice messages are typically <5 MB


@graph_node("preprocess")
async def preprocess_node(state: dict[str, Any]) -> dict[str, Any]:
    raw_input: str = state.get("raw_input", "")
    attachments: list[dict[str, Any]] = state.get("attachments") or []
    message_id: str = state.get("message_id", "")

    if not attachments:
        # ── Branch 1: plain text ──────────────────────────────────────────────
        normalized = raw_input.strip()
        if not normalized:
            raise ForgeError("Empty message — nothing to process", code=400)
        return {"normalized_text": normalized}

    attachment = attachments[0]
    att_type: str = attachment.get("type", "")
    file_key: str = attachment.get("file_key", "")
    att_message_id: str = attachment.get("message_id", message_id)

    if att_type == "audio":
        # ── Branch 2: voice message → ASR ────────────────────────────────────
        from app.integrations.feishu.adapter import FeishuAdapter
        from app.services.asr_service import ASRService

        feishu = FeishuAdapter()
        asr = ASRService(feishu)
        text = await asr.transcribe_voice_message(att_message_id, file_key)
        if not text:
            raise ForgeError("ASR returned empty transcript", code=500)
        logger.info("preprocess_audio_done", message_id=att_message_id, text_len=len(text))
        return {"normalized_text": text}

    if att_type == "file":
        # ── Branch 3: file upload → text extraction ───────────────────────────
        from app.integrations.feishu.adapter import FeishuAdapter
        from app.services.file_extractor import extract_text_from_file

        feishu = FeishuAdapter()
        file_bytes = await feishu.download_message_resource(att_message_id, file_key, type_="file")
        filename: str = attachment.get("file_name", "attachment.txt")
        text = extract_text_from_file(file_bytes, filename)
        if not text.strip():
            raise ForgeError("Extracted file content is empty", code=400)
        logger.info("preprocess_file_done", filename=filename, text_len=len(text))
        return {"normalized_text": text}

    raise ForgeError(f"Unsupported attachment type: '{att_type}'", code=415)
