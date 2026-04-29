import json

from app.services.message_router import parse_message


def _payload(message_type: str, content: dict[str, object], event_id: str = "ev_1") -> dict:
    return {
        "schema": "2.0",
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"user_id": "u_abc"}},
            "message": {
                "message_id": "m_123",
                "chat_id": "c_456",
                "message_type": message_type,
                "content": json.dumps(content),
            },
        },
    }


def test_parse_text_message() -> None:
    msg = parse_message(_payload("text", {"text": "Hello Forge"}))
    assert msg.message_type == "text"
    assert msg.text == "Hello Forge"
    assert msg.message_id == "m_123"
    assert msg.chat_id == "c_456"
    assert msg.sender_user_id == "u_abc"
    assert msg.event_id == "ev_1"


def test_parse_audio_message() -> None:
    msg = parse_message(_payload("audio", {"file_key": "fkey_001"}))
    assert msg.message_type == "audio"
    assert msg.file_key == "fkey_001"
    assert msg.text == ""


def test_parse_unsupported_message() -> None:
    msg = parse_message(_payload("image", {"image_key": "img_001"}))
    assert msg.message_type == "unsupported"
    assert msg.text == ""
    assert msg.file_key == ""


def test_parse_missing_fields_uses_defaults() -> None:
    msg = parse_message({})
    assert msg.event_id == ""
    assert msg.message_id == ""
    assert msg.chat_id == ""
    assert msg.message_type == "unsupported"


def test_parse_text_empty_content() -> None:
    msg = parse_message(_payload("text", {}))
    assert msg.text == ""


def test_parse_invalid_json_content() -> None:
    payload = _payload("text", {})
    payload["event"]["message"]["content"] = "not-json"  # type: ignore[index]
    msg = parse_message(payload)
    assert msg.text == ""
