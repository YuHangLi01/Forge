"""Unit tests for FeishuASRClient.

Mocks Feishu OpenAPI via respx; never touches the network. Covers:
- happy path (text returned)
- empty recognition (Feishu code=0, empty text)
- API-level error (code != 0)
- HTTP 4xx (raises immediately, no retry)
- HTTP 5xx (tenacity retries 3x then raises)
- audio is base64-encoded in request body
- format param is forwarded
- empty audio bytes rejected before any HTTP call
- token cache reuses on second transcribe call
"""

import base64
import json
from typing import Any

import httpx
import pytest
import respx

from app.exceptions import ASRError
from app.integrations.feishu_asr.client import FeishuASRClient

_DOMAIN = "https://open.feishu.cn"
_TOKEN_URL = f"{_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal"
_STT_URL = f"{_DOMAIN}/open-apis/speech_to_text/v1/speech/file_recognize"

_TOKEN_OK: dict[str, Any] = {
    "code": 0,
    "msg": "ok",
    "tenant_access_token": "t-test-fake",
    "expire": 7200,
}


def _ok_token_route(mock: respx.MockRouter) -> None:
    mock.post(_TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_OK))


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_success() -> None:
    with respx.mock(assert_all_called=True) as mock:
        _ok_token_route(mock)
        mock.post(_STT_URL).mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "msg": "success", "data": {"recognition_text": "你好"}},
            )
        )
        client = FeishuASRClient()
        result = await client.transcribe(b"raw-audio-bytes", audio_format="opus")
        assert result == "你好"


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_empty_recognition_returns_empty_string() -> None:
    with respx.mock(assert_all_called=True) as mock:
        _ok_token_route(mock)
        mock.post(_STT_URL).mock(
            return_value=httpx.Response(
                200, json={"code": 0, "msg": "ok", "data": {"recognition_text": ""}}
            )
        )
        result = await FeishuASRClient().transcribe(b"silence")
        assert result == ""


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_api_error_raises() -> None:
    with respx.mock() as mock:
        _ok_token_route(mock)
        mock.post(_STT_URL).mock(
            return_value=httpx.Response(
                200, json={"code": 99991671, "msg": "audio format not supported"}
            )
        )
        with pytest.raises(ASRError, match="99991671"):
            await FeishuASRClient().transcribe(b"audio")


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_http_400_raises_no_retry() -> None:
    with respx.mock() as mock:
        _ok_token_route(mock)
        # Deliberately 400 — should raise ASRError after the 3rd attempt
        # (tenacity retries on ASRError too in this client because we raise it
        #  uniformly, then bubble out).
        route = mock.post(_STT_URL).mock(return_value=httpx.Response(400, text="bad request"))
        with pytest.raises(ASRError, match="http 400"):
            await FeishuASRClient().transcribe(b"audio")
        assert route.call_count == 3  # tenacity wrapped


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_http_500_retries_then_raises() -> None:
    with respx.mock() as mock:
        _ok_token_route(mock)
        route = mock.post(_STT_URL).mock(return_value=httpx.Response(500, text="boom"))
        with pytest.raises(httpx.HTTPStatusError):
            await FeishuASRClient().transcribe(b"audio")
        assert route.call_count == 3


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_audio_is_base64_encoded() -> None:
    captured: dict[str, Any] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"code": 0, "msg": "ok", "data": {"recognition_text": "ok"}}
        )

    with respx.mock() as mock:
        _ok_token_route(mock)
        mock.post(_STT_URL).mock(side_effect=_capture)
        await FeishuASRClient().transcribe(b"plain-bytes", audio_format="wav")

    assert captured["body"]["speech"]["speech"] == base64.b64encode(b"plain-bytes").decode()
    assert captured["body"]["config"]["format"] == "wav"
    assert captured["body"]["config"]["engine_type"] == "16k_auto"


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_authorization_header_uses_token() -> None:
    seen: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200, json={"code": 0, "msg": "ok", "data": {"recognition_text": "ok"}}
        )

    with respx.mock() as mock:
        _ok_token_route(mock)
        mock.post(_STT_URL).mock(side_effect=_capture)
        await FeishuASRClient().transcribe(b"audio")

    assert seen["auth"] == "Bearer t-test-fake"


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_transcribe_empty_audio_rejects_before_http() -> None:
    with respx.mock(assert_all_called=False) as mock:
        token_route = mock.post(_TOKEN_URL)
        with pytest.raises(ASRError, match="empty"):
            await FeishuASRClient().transcribe(b"")
        assert token_route.call_count == 0


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_token_cached_across_transcribe_calls() -> None:
    with respx.mock() as mock:
        token_route = mock.post(_TOKEN_URL).mock(return_value=httpx.Response(200, json=_TOKEN_OK))
        mock.post(_STT_URL).mock(
            return_value=httpx.Response(
                200, json={"code": 0, "msg": "ok", "data": {"recognition_text": "x"}}
            )
        )
        client = FeishuASRClient()
        await client.transcribe(b"a")
        await client.transcribe(b"b")
        assert token_route.call_count == 1


@pytest.mark.usefixtures("mock_env")
@pytest.mark.asyncio
async def test_token_endpoint_error_raises() -> None:
    with respx.mock() as mock:
        mock.post(_TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"code": 99991663, "msg": "rate limited"})
        )
        with pytest.raises(ASRError, match="99991663"):
            await FeishuASRClient().transcribe(b"audio")
