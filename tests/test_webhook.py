import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEISHU_APP_ID", "test_app_id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "test_secret")
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "test_token")
    monkeypatch.setenv("FEISHU_ENCRYPT_KEY", "test_encrypt_key_abc")
    monkeypatch.setenv("DOUBAO_API_KEY", "key")
    monkeypatch.setenv("DOUBAO_BASE_URL", "https://ark.example.com")
    monkeypatch.setenv("DOUBAO_MODEL_PRO", "ep-xxx")
    monkeypatch.setenv("DOUBAO_MODEL_LITE", "ep-yyy")
    monkeypatch.setenv("VOLC_ASR_APP_ID", "asr_id")
    monkeypatch.setenv("VOLC_ASR_ACCESS_TOKEN", "asr_tok")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://forge:forge@localhost/forge")
    monkeypatch.setenv("DATABASE_URL_SYNC", "postgresql+psycopg://forge:forge@localhost/forge")
    from app.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client(mock_settings: None) -> TestClient:
    mock_redis = MagicMock()
    mock_redis.aclose = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch("app.services.event_dedup.set_redis_client"),
    ):
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_webhook_url_verification(client: TestClient) -> None:
    payload = {"type": "url_verification", "challenge": "forge_test_123", "token": "tok"}
    resp = client.post(
        "/api/v1/webhook/feishu",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "forge_test_123"


def test_webhook_url_verification_v2_style(client: TestClient) -> None:
    payload = {"challenge": "v2_challenge", "token": "t"}
    resp = client.post(
        "/api/v1/webhook/feishu",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "v2_challenge"


def test_webhook_invalid_json(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/webhook/feishu",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_webhook_invalid_signature_rejected(client: TestClient) -> None:
    body = json.dumps(
        {"schema": "2.0", "header": {"event_type": "im.message.receive_v1", "event_id": "ev_1"}}
    )
    ts = str(int(time.time()))
    resp = client.post(
        "/api/v1/webhook/feishu",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": ts,
            "X-Lark-Request-Nonce": "nonce",
            "X-Lark-Signature": "invalidsig",
        },
    )
    assert resp.status_code == 401


def test_webhook_valid_message_dispatches_task(client: TestClient) -> None:
    payload = {
        "schema": "2.0",
        "header": {
            "event_type": "im.message.receive_v1",
            "event_id": "ev_unique_001",
            "create_time": "1700000000000",
        },
        "event": {"message": {"message_id": "m1", "message_type": "text", "chat_id": "c1"}},
    }
    body = json.dumps(payload).encode()
    encrypt_key = "test_encrypt_key_abc"
    ts = str(int(time.time()))
    nonce = "testnonce"
    sig = hashlib.sha256((ts + nonce + encrypt_key).encode() + body).hexdigest()

    with (
        patch("app.api.webhook.is_duplicate", new=AsyncMock(return_value=False)),
        patch("app.tasks.message_tasks.handle_message_task") as mock_task,
    ):
        mock_task.delay = MagicMock()
        resp = client.post(
            "/api/v1/webhook/feishu",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Lark-Request-Timestamp": ts,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
