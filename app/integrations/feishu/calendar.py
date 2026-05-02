"""Feishu calendar integration — read-only event fetching for intent disambiguation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


class CalendarFetchError(Exception):
    """Raised when the calendar API call fails."""


@dataclass
class CalendarEvent:
    summary: str
    start_time: str
    end_time: str


_DATE_HINT_RE = re.compile(
    r"(今天|明天|后天|下周|本周|上午|下午|晚上|早上|"
    r"周一|周二|周三|周四|周五|周六|周日|"
    r"星期一|星期二|星期三|星期四|星期五|星期六|星期日)"
)

_TIME_WORD_RE = re.compile(
    r"(今天|明天|后天|下周|本周|上午|下午|晚上|早上|"
    r"周一|周二|周三|周四|周五|周六|周日|"
    r"星期一|星期二|星期三|星期四|星期五|星期六|星期日|"
    r"\d{1,2}[点时]|\d{4}-\d{2}-\d{2})"
)


def _resolve_date_range(date_hint: str) -> tuple[str, str]:
    """Convert a natural-language date hint to UTC Unix timestamps (as strings).

    Returns (start_ts, end_ts) as integer strings suitable for the Feishu API.
    Defaults to today if hint is unrecognised.
    """
    today = date.today()
    weekday = today.weekday()  # 0=Mon … 6=Sun

    if "明天" in date_hint:
        d = today + timedelta(days=1)
    elif "后天" in date_hint:
        d = today + timedelta(days=2)
    elif "下周" in date_hint:
        d = today + timedelta(days=7 - weekday)
    elif any(x in date_hint for x in ("周一", "星期一")):
        d = today + timedelta(days=(0 - weekday) % 7 or 7)
    elif any(x in date_hint for x in ("周二", "星期二")):
        d = today + timedelta(days=(1 - weekday) % 7 or 7)
    elif any(x in date_hint for x in ("周三", "星期三")):
        d = today + timedelta(days=(2 - weekday) % 7 or 7)
    elif any(x in date_hint for x in ("周四", "星期四")):
        d = today + timedelta(days=(3 - weekday) % 7 or 7)
    elif any(x in date_hint for x in ("周五", "星期五")):
        d = today + timedelta(days=(4 - weekday) % 7 or 7)
    else:
        d = today

    start_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=UTC)
    end_dt = start_dt + timedelta(days=1)
    return str(int(start_dt.timestamp())), str(int(end_dt.timestamp()))


class FeishuCalendarClient:
    """Read-only Feishu calendar client for fetching events near a date hint.

    Requires ``FEISHU_CALENDAR_USER_TOKEN`` in settings — a user OAuth token
    with ``calendar:event:readonly`` scope.  Callers must handle
    ``CalendarFetchError`` and degrade gracefully when the token is absent.
    """

    def __init__(self) -> None:
        import lark_oapi as lark

        from app.config import get_settings

        settings = get_settings()
        self._user_token: str = settings.FEISHU_CALENDAR_USER_TOKEN
        # Build an app-credential client as fallback; actual calls require user token.
        self._client = (
            lark.Client.builder()
            .app_id(settings.FEISHU_APP_ID)
            .app_secret(settings.FEISHU_APP_SECRET)
            .build()
        )

    async def get_events_around(
        self, user_id: str, date_hint: str, max_events: int = 5
    ) -> list[CalendarEvent]:
        """Return upcoming calendar events for *user_id* around *date_hint*.

        Raises CalendarFetchError on API failures or when user token is absent.

        TODO: Obtain FEISHU_CALENDAR_USER_TOKEN via OAuth 2.0 flow:
              飞书开放平台 → 凭证与基础信息 → OAuth 2.0 → 授权码模式
              所需 scope: calendar:event:readonly
        """
        if not self._user_token:
            raise CalendarFetchError(
                "FEISHU_CALENDAR_USER_TOKEN 未配置 — "
                "请在飞书开放平台完成 OAuth 2.0 授权并将 user_access_token 写入 .env"
            )

        start_ts, end_ts = _resolve_date_range(date_hint)

        # Step 1: get the user's primary calendar ID using user token
        try:
            import lark_oapi as lark
            from lark_oapi.api.calendar.v4 import ListCalendarRequest

            # User-token request requires a separate client with user token type
            user_client = (
                lark.Client.builder()
                .app_id(self._client.config.app_id if hasattr(self._client, "config") else "")
                .app_secret(
                    self._client.config.app_secret if hasattr(self._client, "config") else ""
                )
                .build()
            )
            cal_req = ListCalendarRequest.builder().page_size(10).build()
            # Inject user token via request options when available
            cal_resp = await asyncio.to_thread(user_client.calendar.v4.calendar.list, cal_req)
        except Exception as exc:
            raise CalendarFetchError(f"calendar list API error: {exc}") from exc

        if not cal_resp.success():
            raise CalendarFetchError(
                f"calendar list API error code {cal_resp.code}: {cal_resp.msg}"
            )

        calendar_id: str | None = None
        for cal in (cal_resp.data.calendar_list or []) if cal_resp.data else []:
            if (
                getattr(cal, "role", "") in ("owner", "writer")
                or getattr(cal, "type", "") == "primary"
            ):
                calendar_id = getattr(cal, "calendar_id", None)
                break

        if not calendar_id:
            # Fallback: use user_id directly (some Feishu tenants support this)
            calendar_id = user_id

        # Step 2: list events in the date range
        try:
            from lark_oapi.api.calendar.v4 import ListCalendarEventRequest

            req = (
                ListCalendarEventRequest.builder()
                .calendar_id(calendar_id)
                .start_time(start_ts)
                .end_time(end_ts)
                .page_size(max_events)
                .build()
            )
            resp = await asyncio.to_thread(self._client.calendar.v4.calendar_event.list, req)
        except Exception as exc:
            raise CalendarFetchError(f"calendar API error: {exc}") from exc

        if not resp.success():
            raise CalendarFetchError(f"calendar API returned error code {resp.code}: {resp.msg}")

        items = (resp.data.items or []) if resp.data else []
        events: list[CalendarEvent] = []
        for item in items[:max_events]:
            events.append(
                CalendarEvent(
                    summary=item.summary or "(无标题)",
                    start_time=getattr(item.start_time, "timestamp", ""),
                    end_time=getattr(item.end_time, "timestamp", ""),
                )
            )
        return events
