from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ParsedMessage:
    event_id: str
    message_id: str
    chat_id: str
    sender_user_id: str
    message_type: Literal["text", "audio", "unsupported"]
    text: str
    file_key: str


def parse_message(payload: dict[str, Any]) -> ParsedMessage:
    header = payload.get("header") or {}
    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}

    event_id: str = header.get("event_id", "")
    message_id: str = message.get("message_id", "")
    chat_id: str = message.get("chat_id", "")
    sender_user_id: str = sender.get("sender_id", {}).get("user_id", "")
    raw_type: str = message.get("message_type", "")
    content = message.get("content") or "{}"

    import json

    try:
        content_obj: dict[str, Any] = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        content_obj = {}

    if raw_type == "text":
        return ParsedMessage(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            sender_user_id=sender_user_id,
            message_type="text",
            text=content_obj.get("text", ""),
            file_key="",
        )
    if raw_type == "audio":
        return ParsedMessage(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            sender_user_id=sender_user_id,
            message_type="audio",
            text="",
            file_key=content_obj.get("file_key", ""),
        )
    return ParsedMessage(
        event_id=event_id,
        message_id=message_id,
        chat_id=chat_id,
        sender_user_id=sender_user_id,
        message_type="unsupported",
        text="",
        file_key="",
    )
