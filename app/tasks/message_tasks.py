import asyncio
import json
from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)


@forge_task(name="forge.handle_message", queue="slow")  # type: ignore[untyped-decorator]
def handle_message_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    event = payload.get("event", {})
    message = event.get("message", {}) if isinstance(event, dict) else {}
    raw_header = payload.get("header")
    event_id = raw_header.get("event_id", "") if isinstance(raw_header, dict) else ""

    logger.info("message_received", event_id=event_id, message_type=message.get("message_type"))

    return asyncio.run(_handle_message_async(payload))


async def _handle_message_async(payload: dict[str, Any]) -> dict[str, Any]:
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.services.asr_service import ASRService
    from app.services.echo_responder import EchoResponder
    from app.services.intent_router import classify
    from app.services.message_router import parse_message

    msg = parse_message(payload)

    feishu = FeishuAdapter()
    asr_svc = ASRService(feishu)  # defaults to FeishuASRClient (Stage 1)
    responder = EchoResponder()

    user_text = msg.text

    if msg.message_type == "audio" and msg.file_key:
        user_text = await asr_svc.transcribe_voice_message(msg.message_id, msg.file_key)
        if not user_text:
            user_text = "[语音内容无法识别]"

    if msg.message_type == "unsupported":
        logger.info("unsupported_message_type", message_id=msg.message_id)
        return {"status": "received", "message_type": "unsupported"}

    if not user_text.strip():
        return {"status": "received", "message_type": msg.message_type}

    intent = classify(user_text)
    if intent == "generate_demo":
        from app.tasks.demo_tasks import handle_demo_request_task

        handle_demo_request_task.delay(payload)
        logger.info("demo_task_dispatched", message_id=msg.message_id, text=user_text)
        return {"status": "dispatched", "intent": "generate_demo"}

    try:
        reply = await responder.respond(msg.chat_id, msg.message_id, user_text)
        if msg.message_id:
            await feishu.reply_text(msg.message_id, reply)
        else:
            await feishu.send_text(msg.chat_id, reply)
    except Exception as exc:
        logger.exception("message_handler_failed", message_id=msg.message_id, error=str(exc))
        _error_reply = "抱歉，处理出错，请稍后重试。"
        try:
            if msg.message_id:
                await feishu.reply_text(msg.message_id, _error_reply)
            else:
                await feishu.send_text(msg.chat_id, _error_reply)
        except Exception:
            logger.exception("error_reply_failed", message_id=msg.message_id)
        return {"status": "error", "error": str(exc)}

    return {"status": "completed", "message_id": msg.message_id}


def _parse_message_content(raw_content: str | None, message_type: str) -> str:
    if not raw_content:
        return ""
    try:
        obj: dict[str, Any] = json.loads(raw_content)
        if message_type == "text":
            return str(obj.get("text", ""))
        if message_type == "audio":
            return str(obj.get("file_key", ""))
    except (json.JSONDecodeError, TypeError):
        pass
    return ""
