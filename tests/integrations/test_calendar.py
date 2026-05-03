"""Tests for calendar context utilities and FeishuCalendarClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.feishu.calendar import CalendarEvent, CalendarFetchError
from app.services.calendar_context import format_events_for_prompt, has_time_word

# ── has_time_word ─────────────────────────────────────────────────────────────


def test_has_time_word_detects_明天() -> None:
    assert has_time_word("明天上午开个会") is True


def test_has_time_word_detects_今天() -> None:
    assert has_time_word("今天下午有什么安排") is True


def test_has_time_word_detects_下周() -> None:
    assert has_time_word("下周一发一份报告") is True


def test_has_time_word_detects_clock_time() -> None:
    assert has_time_word("下午3点开会") is True


def test_has_time_word_detects_iso_date() -> None:
    assert has_time_word("2026-05-10 有个演示") is True


def test_has_time_word_no_match() -> None:
    assert has_time_word("帮我写一份市场分析报告") is False
    assert has_time_word("") is False


# ── format_events_for_prompt ──────────────────────────────────────────────────


def test_format_events_for_prompt_empty() -> None:
    assert format_events_for_prompt([]) == ""


def test_format_events_for_prompt_single_event() -> None:
    events = [CalendarEvent(summary="季度复盘会议", start_time="1746835200", end_time="1746842400")]
    result = format_events_for_prompt(events)
    assert "季度复盘会议" in result
    assert "相关日程" in result


def test_format_events_for_prompt_multiple_events() -> None:
    events = [
        CalendarEvent(summary="A会议", start_time="1", end_time="2"),
        CalendarEvent(summary="B演示", start_time="3", end_time="4"),
    ]
    result = format_events_for_prompt(events)
    assert "A会议" in result
    assert "B演示" in result


# ── FeishuCalendarClient ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_time_word_skips_calendar() -> None:
    """intent_parser should NOT call calendar when no time word is present."""
    from app.graph.nodes.intent_parser import intent_parser_node
    from app.schemas.intent import IntentSchema

    state = {
        "message_id": "msg1",
        "user_id": "usr1",
        "normalized_text": "帮我写一份市场分析报告",
    }

    fake_intent = IntentSchema(
        task_type="create_new",
        primary_goal="市场分析报告",
        output_formats=["document"],
        ambiguity_score=0.1,
    )

    with patch(
        "app.services.llm_service.LLMService.structured", new_callable=AsyncMock
    ) as mock_llm:
        mock_llm.return_value = fake_intent
        result = await intent_parser_node(state)

    assert result["intent"].primary_goal == "市场分析报告"
    assert not has_time_word("帮我写一份市场分析报告")


@pytest.mark.asyncio
async def test_single_event_no_clarify() -> None:
    """One matching event should populate calendar_context but not force ambiguity."""
    from app.graph.nodes.intent_parser import intent_parser_node
    from app.integrations.feishu.calendar import CalendarEvent
    from app.schemas.intent import IntentSchema

    state = {
        "message_id": "msg2",
        "user_id": "usr2",
        "normalized_text": "明天开会前准备一份简报",
    }

    fake_event = CalendarEvent(summary="明天晨会", start_time="1746835200", end_time="1746839200")
    fake_intent = IntentSchema(
        task_type="create_new",
        primary_goal="会议简报",
        output_formats=["document"],
        ambiguity_score=0.2,
    )

    with (
        patch(
            "app.integrations.feishu.calendar.FeishuCalendarClient.get_events_around",
            new_callable=AsyncMock,
            return_value=[fake_event],
        ),
        patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = fake_intent
        result = await intent_parser_node(state)

    assert result["intent"].ambiguity_score == 0.2


@pytest.mark.asyncio
async def test_calendar_api_failure_degrades() -> None:
    """Calendar API failure should fall back to V1 prompt, not crash."""
    from app.graph.nodes.intent_parser import intent_parser_node
    from app.schemas.intent import IntentSchema

    state = {
        "message_id": "msg3",
        "user_id": "usr3",
        "normalized_text": "明天下午开个产品评审会",
    }

    fake_intent = IntentSchema(
        task_type="create_new",
        primary_goal="产品评审会准备",
        output_formats=["document"],
        ambiguity_score=0.3,
    )

    with (
        patch(
            "app.integrations.feishu.calendar.FeishuCalendarClient.get_events_around",
            new_callable=AsyncMock,
            side_effect=CalendarFetchError("API timeout"),
        ),
        patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = fake_intent
        result = await intent_parser_node(state)

    assert "intent" in result


@pytest.mark.asyncio
async def test_multiple_events_trigger_higher_ambiguity() -> None:
    """Two+ events with ambiguous message — LLM can set ambiguity ≥ 0.7."""
    from app.graph.nodes.intent_parser import intent_parser_node
    from app.integrations.feishu.calendar import CalendarEvent
    from app.schemas.intent import IntentSchema

    state = {
        "message_id": "msg4",
        "user_id": "usr4",
        "normalized_text": "明天开会前整理一下资料",
    }

    events = [
        CalendarEvent(summary="技术评审会", start_time="1", end_time="2"),
        CalendarEvent(summary="产品周会", start_time="3", end_time="4"),
    ]
    fake_intent = IntentSchema(
        task_type="create_new",
        primary_goal="会议资料整理",
        output_formats=["document"],
        ambiguity_score=0.75,
        missing_info=["请确认是哪个会议：技术评审会还是产品周会？"],
    )

    with (
        patch(
            "app.integrations.feishu.calendar.FeishuCalendarClient.get_events_around",
            new_callable=AsyncMock,
            return_value=events,
        ),
        patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock_llm,
    ):
        mock_llm.return_value = fake_intent
        result = await intent_parser_node(state)

    assert result["intent"].ambiguity_score >= 0.7


# ── _resolve_date_range full coverage ─────────────────────────────────────────


def test_resolve_date_range_tomorrow() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("明天开会")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_day_after_tomorrow() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("后天有空")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_next_week() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("下周一会议")
    assert int(end) > int(start)


def test_resolve_date_range_monday() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("周一上午")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_tuesday() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("周二有空")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_wednesday() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("周三下午")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_thursday() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("周四会议")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_friday() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("周五上午会议")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_xinqi_one() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("星期一开会")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_xinqi_two() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("星期二上午")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_xinqi_three() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("星期三有空")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_xinqi_four() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("星期四会议")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_xinqi_five() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("星期五下午")
    assert int(end) - int(start) == 86400


def test_resolve_date_range_unknown_defaults_today() -> None:
    from app.integrations.feishu.calendar import _resolve_date_range

    start, end = _resolve_date_range("随便什么时间")
    assert int(end) - int(start) == 86400


# ── FeishuCalendarClient error paths ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_client_raises_without_token() -> None:
    from unittest.mock import MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = ""
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import CalendarFetchError, FeishuCalendarClient

        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="FEISHU_CALENDAR_USER_TOKEN"):
            await client.get_events_around("u1", "今天")


@pytest.mark.asyncio
async def test_client_api_exception_wraps_error() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = "tok"
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
        patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=RuntimeError("down")),
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import CalendarFetchError, FeishuCalendarClient

        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="calendar list API error"):
            await client.get_events_around("u1", "今天")


@pytest.mark.asyncio
async def test_client_cal_list_failure_code_raises() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = "tok"
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    mock_resp = MagicMock()
    mock_resp.success.return_value = False
    mock_resp.code = 403
    mock_resp.msg = "Forbidden"

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
        patch("asyncio.to_thread", new_callable=AsyncMock, return_value=mock_resp),
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import CalendarFetchError, FeishuCalendarClient

        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="403"):
            await client.get_events_around("u1", "今天")


@pytest.mark.asyncio
async def test_client_success_returns_events() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = "tok"
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    mock_cal_resp = MagicMock()
    mock_cal_resp.success.return_value = True
    mock_cal_resp.data = MagicMock()
    mock_cal = MagicMock()
    mock_cal.role = "owner"
    mock_cal.calendar_id = "cal1"
    mock_cal_resp.data.calendar_list = [mock_cal]

    mock_event = MagicMock()
    mock_event.summary = "Daily Standup"
    mock_event.start_time.timestamp = "1700000000"
    mock_event.end_time.timestamp = "1700003600"

    mock_evt_resp = MagicMock()
    mock_evt_resp.success.return_value = True
    mock_evt_resp.data = MagicMock()
    mock_evt_resp.data.items = [mock_event]

    call_count = 0

    async def mock_to_thread(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_cal_resp if call_count == 1 else mock_evt_resp

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
        patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=mock_to_thread),
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import FeishuCalendarClient

        client = FeishuCalendarClient()
        events = await client.get_events_around("u1", "今天")
    assert len(events) == 1
    assert events[0].summary == "Daily Standup"


@pytest.mark.asyncio
async def test_client_no_calendar_fallback_to_user_id() -> None:
    """When calendar list is empty, falls back to user_id as calendar_id."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = "tok"
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    mock_cal_resp = MagicMock()
    mock_cal_resp.success.return_value = True
    mock_cal_resp.data = MagicMock()
    mock_cal_resp.data.calendar_list = []

    mock_evt_resp = MagicMock()
    mock_evt_resp.success.return_value = True
    mock_evt_resp.data = MagicMock()
    mock_evt_resp.data.items = []

    call_count = 0

    async def mock_to_thread(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_cal_resp if call_count == 1 else mock_evt_resp

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
        patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=mock_to_thread),
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import FeishuCalendarClient

        client = FeishuCalendarClient()
        events = await client.get_events_around("u1", "今天")
    assert events == []


@pytest.mark.asyncio
async def test_client_event_list_exception_raises() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = "tok"
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    mock_cal_resp = MagicMock()
    mock_cal_resp.success.return_value = True
    mock_cal_resp.data = MagicMock()
    mock_cal = MagicMock()
    mock_cal.role = "owner"
    mock_cal.calendar_id = "cal1"
    mock_cal_resp.data.calendar_list = [mock_cal]

    call_count = 0

    async def mock_to_thread(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_cal_resp
        raise RuntimeError("event list failed")

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
        patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=mock_to_thread),
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import CalendarFetchError, FeishuCalendarClient

        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="calendar API error"):
            await client.get_events_around("u1", "今天")


@pytest.mark.asyncio
async def test_client_event_list_resp_failure_raises() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_settings = MagicMock()
    mock_settings.FEISHU_CALENDAR_USER_TOKEN = "tok"
    mock_settings.FEISHU_APP_ID = "app1"
    mock_settings.FEISHU_APP_SECRET = "secret1"

    mock_cal_resp = MagicMock()
    mock_cal_resp.success.return_value = True
    mock_cal_resp.data = MagicMock()
    mock_cal = MagicMock()
    mock_cal.role = "owner"
    mock_cal.calendar_id = "cal1"
    mock_cal_resp.data.calendar_list = [mock_cal]

    mock_evt_resp = MagicMock()
    mock_evt_resp.success.return_value = False
    mock_evt_resp.code = 404
    mock_evt_resp.msg = "Not Found"

    call_count = 0

    async def mock_to_thread(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_cal_resp if call_count == 1 else mock_evt_resp

    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("lark_oapi.Client") as mock_lark,
        patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=mock_to_thread),
    ):
        mock_builder = MagicMock()
        mock_lark.builder.return_value = mock_builder
        mock_builder.app_id.return_value = mock_builder
        mock_builder.app_secret.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        from app.integrations.feishu.calendar import CalendarFetchError, FeishuCalendarClient

        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="404"):
            await client.get_events_around("u1", "今天")
