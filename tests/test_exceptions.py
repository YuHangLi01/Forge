from app.exceptions import (
    ASRError,
    CheckpointError,
    FeishuAPIError,
    FeishuRateLimitError,
    ForgeError,
    IntentParseError,
    LLMError,
)


def test_forge_error_base() -> None:
    err = ForgeError("something failed", code=42)
    assert str(err) == "something failed"
    assert err.message == "something failed"
    assert err.code == 42


def test_forge_error_default_code() -> None:
    err = ForgeError("fail")
    assert err.code == -1


def test_intent_parse_error_is_forge_error() -> None:
    err = IntentParseError("bad intent")
    assert isinstance(err, ForgeError)
    assert err.message == "bad intent"


def test_feishu_api_error() -> None:
    err = FeishuAPIError("feishu fail", feishu_code=99991663)
    assert err.feishu_code == 99991663
    assert isinstance(err, ForgeError)


def test_feishu_rate_limit_error_hierarchy() -> None:
    err = FeishuRateLimitError("rate limited", feishu_code=99991663)
    assert isinstance(err, FeishuAPIError)
    assert isinstance(err, ForgeError)


def test_asr_error() -> None:
    err = ASRError("asr timeout")
    assert isinstance(err, ForgeError)


def test_llm_error() -> None:
    err = LLMError("llm unavailable")
    assert isinstance(err, ForgeError)


def test_checkpoint_error() -> None:
    err = CheckpointError("pg save failed")
    assert isinstance(err, ForgeError)
