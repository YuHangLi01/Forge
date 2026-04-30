"""Tests for the demo generation pipeline.

The Celery wrapper itself is one-line (asyncio.run); all interesting logic
lives in `_handle_demo_async` and `_build_demo`. We unit-test those
directly with a fully mocked FeishuAdapter to avoid network.

Coverage targets:
- pick_fixture is deterministic
- _build_demo calls Doc + PPT services and Drive upload in the right order
- _handle_demo_async sends pre-reply + final reply with both share URLs
- failure path: an exception in _build_demo triggers an apology reply
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.demo_tasks import _build_demo, _handle_demo_async, pick_fixture


def _make_payload(text: str = "生成PPT", message_id: str = "om_test") -> dict:
    return {
        "header": {"event_id": "evt_1", "event_type": "im.message.receive_v1"},
        "event": {
            "message": {
                "message_id": message_id,
                "chat_id": "oc_chat",
                "message_type": "text",
                "content": f'{{"text":"{text}"}}',
            },
            "sender": {"sender_id": {"open_id": "ou_user"}},
        },
    }


def test_pick_fixture_deterministic() -> None:
    a = pick_fixture("om_abc")
    b = pick_fixture("om_abc")
    assert a == b
    assert a in (
        "01_requirements",
        "02_granularity",
        "03_midterm_review",
        "04_project_pr",
        "05_defense",
    )


def test_pick_fixture_varies_with_seed() -> None:
    seen = {pick_fixture(f"seed-{i}") for i in range(20)}
    # 20 different seeds should land on at least 3 distinct fixtures
    assert len(seen) >= 3


@pytest.mark.asyncio
async def test_build_demo_calls_doc_and_pptx_and_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    feishu = AsyncMock()
    feishu.upload_drive_file.return_value = "fake-pptx-token"
    feishu.get_share_url.return_value = "https://open.feishu.cn/file/fake-pptx-token"

    fake_doc_artifact = MagicMock(
        doc_id="fake-doc-token",
        share_url="https://open.feishu.cn/docx/fake-doc-token",
    )

    fake_doc_service = AsyncMock()
    fake_doc_service.create_from_markdown.return_value = fake_doc_artifact
    fake_doc_service_cls = MagicMock(return_value=fake_doc_service)
    monkeypatch.setattr("app.services.feishu_doc_service.FeishuDocService", fake_doc_service_cls)

    fake_ppt_service = AsyncMock()
    fake_ppt_service.build_pptx_bytes.return_value = b"PK\x03\x04fakepptx"
    fake_ppt_service_cls = MagicMock(return_value=fake_ppt_service)
    monkeypatch.setattr("app.services.ppt_service.PPTService", fake_ppt_service_cls)

    result = await _build_demo(feishu, "01_requirements", "需求确定会会议纪要")

    assert result["doc_token"] == "fake-doc-token"
    assert result["pptx_token"] == "fake-pptx-token"
    assert result["doc_share_url"].endswith("fake-doc-token")
    assert result["pptx_share_url"].endswith("fake-pptx-token")
    fake_doc_service.create_from_markdown.assert_awaited_once()
    fake_ppt_service.build_pptx_bytes.assert_awaited_once()
    feishu.upload_drive_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_demo_missing_fixture_raises() -> None:
    feishu = AsyncMock()
    with pytest.raises(FileNotFoundError):
        await _build_demo(feishu, "no_such_fixture", "X")


@pytest.mark.asyncio
async def test_handle_demo_async_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    feishu_instance = AsyncMock()
    monkeypatch.setattr(
        "app.integrations.feishu.adapter.FeishuAdapter",
        MagicMock(return_value=feishu_instance),
    )

    async def _fake_build(_feishu: object, fixture: str, _title: str) -> dict[str, str]:
        return {
            "fixture": fixture,
            "doc_token": "tok-doc",
            "doc_share_url": "https://doc",
            "pptx_token": "tok-ppt",
            "pptx_share_url": "https://ppt",
        }

    monkeypatch.setattr("app.tasks.demo_tasks._build_demo", _fake_build)

    result = await _handle_demo_async(_make_payload())
    assert result["status"] == "completed"
    assert result["doc_share_url"] == "https://doc"
    assert result["pptx_share_url"] == "https://ppt"

    # 1 pre-reply + 1 final reply = 2 calls
    assert feishu_instance.reply_text.await_count == 2
    final_args = feishu_instance.reply_text.await_args_list[-1].args
    assert "https://doc" in final_args[1]
    assert "https://ppt" in final_args[1]


@pytest.mark.asyncio
async def test_handle_demo_async_apology_on_build_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feishu_instance = AsyncMock()
    monkeypatch.setattr(
        "app.integrations.feishu.adapter.FeishuAdapter",
        MagicMock(return_value=feishu_instance),
    )

    async def _bad_build(_feishu: object, _fixture: str, _title: str) -> dict[str, str]:
        raise RuntimeError("scope missing")

    monkeypatch.setattr("app.tasks.demo_tasks._build_demo", _bad_build)

    result = await _handle_demo_async(_make_payload())
    assert result["status"] == "error"
    assert "scope missing" in result["error"]
    # last reply should be the apology
    final_args = feishu_instance.reply_text.await_args_list[-1].args
    assert "失败" in final_args[1] or "scope" in final_args[1]
