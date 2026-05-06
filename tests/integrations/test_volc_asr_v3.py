"""Unit tests for VolcASRV3Client HTTP response parsing.

Uses respx to mock the Volcengine HTTP endpoints so no real network calls.
Key contract: the bigmodel API wraps status under {"resp": {"code": ..., "msg": ...}};
our client must unwrap that layer, not look for code at the top level.
"""

from unittest.mock import patch

import pytest
import respx
from httpx import Response

from app.exceptions import ASRError
from app.integrations.volc_asr.client_v3 import (
    _CODE_PROCESSING,
    _CODE_SUCCESS,
    _QUERY_URL,
    _SUBMIT_URL,
    VolcASRV3Client,
)

_FAKE_ENV = {
    "VOLC_ASR_APP_ID": "app_key",
    "VOLC_ASR_ACCESS_TOKEN": "access_key",
    "VOLC_ASR_RESOURCE_ID": "resource_id",
    "FORGE_PUBLIC_URL": "https://forge.example.com",
    "REDIS_URL": "redis://localhost:6379/0",
}


@pytest.fixture()
def client() -> VolcASRV3Client:
    with patch.dict("os.environ", _FAKE_ENV, clear=False):
        from app.config import get_settings

        get_settings.cache_clear()  # type: ignore[attr-defined]
        c = VolcASRV3Client()
        yield c
        get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture()
def _mock_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out Redis so we don't need a real server."""

    async def _fake_store(self: VolcASRV3Client, audio_bytes: bytes) -> str:  # noqa: ARG001
        return "test_token_abc"

    monkeypatch.setattr(VolcASRV3Client, "_store_audio", _fake_store)


@pytest.mark.asyncio
@respx.mock
async def test_submit_resp_nested_code_success(
    client: VolcASRV3Client,
    _mock_redis: None,
) -> None:
    """submit returns {"resp": {"code": 20000001, "msg": "success"}} → proceeds to poll."""
    respx.post(_SUBMIT_URL).mock(
        return_value=Response(
            200,
            json={"resp": {"code": _CODE_PROCESSING, "msg": "success"}, "id": "req-1"},
        )
    )
    respx.post(_QUERY_URL).mock(
        return_value=Response(
            200,
            json={
                "resp": {"code": _CODE_SUCCESS, "msg": "success"},
                "result": {"text": "你好世界"},
            },
        )
    )

    result = await client.transcribe(b"audio", audio_format="ogg")
    assert result == "你好世界"


@pytest.mark.asyncio
@respx.mock
async def test_submit_top_level_code_none_raises(
    client: VolcASRV3Client,
    _mock_redis: None,
) -> None:
    """If resp wrapper is missing (old flat format) → raises ASRError with code=None."""
    respx.post(_SUBMIT_URL).mock(return_value=Response(200, json={"code": None, "message": None}))

    with pytest.raises(ASRError, match="submit rejected.*code=None"):
        await client.transcribe(b"audio", audio_format="ogg")


@pytest.mark.asyncio
@respx.mock
async def test_submit_rejected_non_processing_code_raises(
    client: VolcASRV3Client,
    _mock_redis: None,
) -> None:
    """A non-processing code in resp → raises ASRError with the error code."""
    respx.post(_SUBMIT_URL).mock(
        return_value=Response(
            200,
            json={"resp": {"code": 45000001, "msg": "invalid param"}},
        )
    )

    with pytest.raises(ASRError, match="submit rejected.*code=45000001"):
        await client.transcribe(b"audio", audio_format="ogg")


@pytest.mark.asyncio
@respx.mock
async def test_query_error_code_raises(
    client: VolcASRV3Client,
    _mock_redis: None,
) -> None:
    """A non-success code during polling → raises ASRError."""
    respx.post(_SUBMIT_URL).mock(
        return_value=Response(
            200,
            json={"resp": {"code": _CODE_PROCESSING, "msg": "success"}, "id": "req-2"},
        )
    )
    respx.post(_QUERY_URL).mock(
        return_value=Response(
            200,
            json={"resp": {"code": 45000002, "msg": "audio decode error"}},
        )
    )

    with pytest.raises(ASRError, match="volc_asr_v3 error.*code=45000002"):
        await client.transcribe(b"audio", audio_format="ogg")


@pytest.mark.asyncio
@respx.mock
async def test_submit_http_error_raises(
    client: VolcASRV3Client,
    _mock_redis: None,
) -> None:
    """Non-200 HTTP from submit → ASRError with status code in message."""
    respx.post(_SUBMIT_URL).mock(return_value=Response(401, text="Unauthorized"))

    with pytest.raises(ASRError, match="submit http 401"):
        await client.transcribe(b"audio", audio_format="ogg")
