from app.schemas.feishu_event import (
    FeishuEventBody,
    FeishuEventHeader,
    FeishuMessage,
    FeishuSender,
    FeishuSenderId,
    FeishuWebhookPayload,
)


def test_feishu_webhook_url_verification() -> None:
    payload = FeishuWebhookPayload.model_validate(
        {"type": "url_verification", "challenge": "abc123", "token": "tok"}
    )
    assert payload.challenge == "abc123"
    assert payload.type == "url_verification"


def test_feishu_webhook_message_event() -> None:
    raw = {
        "schema": "2.0",
        "header": {
            "event_id": "ev_001",
            "event_type": "im.message.receive_v1",
            "create_time": "1700000000000",
            "token": "tok",
            "app_id": "app_id",
            "tenant_key": "tenant",
        },
        "event": {
            "sender": {
                "sender_id": {"user_id": "u1", "open_id": "ou_xxx", "union_id": "on_xxx"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_001",
                "message_type": "text",
                "chat_id": "oc_xxx",
                "chat_type": "group",
                "content": '{"text":"hello"}',
            },
        },
    }
    payload = FeishuWebhookPayload.model_validate(raw)
    assert payload.header.event_id == "ev_001"
    assert payload.header.event_type == "im.message.receive_v1"
    assert payload.event is not None
    assert payload.event.message.message_type == "text"
    assert payload.event.sender.sender_id.user_id == "u1"


def test_feishu_webhook_empty_event() -> None:
    payload = FeishuWebhookPayload.model_validate({"schema": "2.0"})
    assert payload.event is None
    assert payload.challenge is None


def test_feishu_sender_defaults() -> None:
    sender = FeishuSender()
    assert sender.sender_type == ""
    assert sender.sender_id.user_id == ""


def test_feishu_message_defaults() -> None:
    msg = FeishuMessage()
    assert msg.content == "{}"
    assert msg.message_type == ""


def test_feishu_event_header_fields() -> None:
    header = FeishuEventHeader(
        event_id="ev_123",
        event_type="im.message.receive_v1",
        create_time="1700000000",
        token="t",
        app_id="app",
        tenant_key="tk",
    )
    assert header.event_id == "ev_123"


def test_feishu_event_body_with_extra_fields() -> None:
    body = FeishuEventBody.model_validate(
        {
            "sender": {"sender_id": {}, "sender_type": "user"},
            "message": {"message_id": "m1", "message_type": "text"},
            "extra_field": "ignored_but_allowed",
        }
    )
    assert body.message.message_id == "m1"


def test_feishu_sender_id_fields() -> None:
    sid = FeishuSenderId(user_id="u1", open_id="ou1", union_id="un1")
    assert sid.user_id == "u1"
    assert sid.open_id == "ou1"
