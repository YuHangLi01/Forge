"""Tests for calendar context utilities and FeishuCalendarClient."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

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


_CAL_LIST_RE = re.compile(r"https://open\.feishu\.cn/open-apis/calendar/v4/calendars(\?.*)?$")
_EVENTS_RE = re.compile(
    r"https://open\.feishu\.cn/open-apis/calendar/v4/calendars/[^/]+/events(\?.*)?"
)
_OWNED_PRIMARY_CAL = {
    "calendar_id": "cal1",
    "role": "owner",
    "type": "primary",
    "summary": "test",
}


@pytest.mark.asyncio
async def test_client_raises_without_token() -> None:
    from app.integrations.feishu.calendar import FeishuCalendarClient

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value=None,
    ):
        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="未完成飞书日历授权"):
            await client.get_events_around("u1", "今天", AsyncMock())


@pytest.mark.asyncio
@respx.mock
async def test_client_api_exception_wraps_error() -> None:
    """Network failure on /calendars wraps into CalendarFetchError."""
    from app.integrations.feishu.calendar import FeishuCalendarClient

    respx.get(_CAL_LIST_RE).mock(side_effect=httpx.ConnectError("down"))

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="calendar list API error"):
            await client.get_events_around("u1", "今天", AsyncMock())


@pytest.mark.asyncio
@respx.mock
async def test_client_cal_list_failure_code_raises() -> None:
    """Feishu returns non-zero code on /calendars → CalendarFetchError carries the code."""
    from app.integrations.feishu.calendar import FeishuCalendarClient

    respx.get(_CAL_LIST_RE).mock(
        return_value=httpx.Response(200, json={"code": 403, "msg": "Forbidden"})
    )

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="403"):
            await client.get_events_around("u1", "今天", AsyncMock())


@pytest.mark.asyncio
@respx.mock
async def test_client_success_returns_events() -> None:
    from app.integrations.feishu.calendar import FeishuCalendarClient

    respx.get(_CAL_LIST_RE).mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "data": {"calendar_list": [_OWNED_PRIMARY_CAL]}},
        )
    )
    respx.get(_EVENTS_RE).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "items": [
                        {
                            "summary": "Daily Standup",
                            "start_time": {"timestamp": "1700000000"},
                            "end_time": {"timestamp": "1700003600"},
                        }
                    ]
                },
            },
        )
    )

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        client = FeishuCalendarClient()
        events = await client.get_events_around("u1", "今天", AsyncMock())

    assert len(events) == 1
    assert events[0].summary == "Daily Standup"


@pytest.mark.asyncio
@respx.mock
async def test_client_empty_calendar_list_raises() -> None:
    """When the user has no owned calendar, raise loudly (don't silent-fallback to user_id)."""
    from app.integrations.feishu.calendar import FeishuCalendarClient

    respx.get(_CAL_LIST_RE).mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"calendar_list": []}})
    )

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="role=owner"):
            await client.get_events_around("u1", "今天", AsyncMock())


@pytest.mark.asyncio
@respx.mock
async def test_client_event_list_exception_raises() -> None:
    from app.integrations.feishu.calendar import FeishuCalendarClient

    respx.get(_CAL_LIST_RE).mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "data": {"calendar_list": [_OWNED_PRIMARY_CAL]}},
        )
    )
    respx.get(_EVENTS_RE).mock(side_effect=httpx.ConnectError("event list failed"))

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="calendar API error"):
            await client.get_events_around("u1", "今天", AsyncMock())


@pytest.mark.asyncio
@respx.mock
async def test_client_event_list_resp_failure_raises() -> None:
    from app.integrations.feishu.calendar import FeishuCalendarClient

    respx.get(_CAL_LIST_RE).mock(
        return_value=httpx.Response(
            200,
            json={"code": 0, "data": {"calendar_list": [_OWNED_PRIMARY_CAL]}},
        )
    )
    respx.get(_EVENTS_RE).mock(
        return_value=httpx.Response(200, json={"code": 404, "msg": "Not Found"})
    )

    with patch(
        "app.integrations.feishu.oauth.get_valid_token",
        new_callable=AsyncMock,
        return_value="tok",
    ):
        client = FeishuCalendarClient()
        with pytest.raises(CalendarFetchError, match="404"):
            await client.get_events_around("u1", "今天", AsyncMock())
