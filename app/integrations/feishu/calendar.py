"""Feishu calendar integration — read-only event fetching for intent disambiguation."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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

    Tokens are fetched per-user from the DB via get_valid_token(); no global
    env token is required.  Callers must handle CalendarFetchError and degrade
    gracefully (e.g. send an OAuth authorization link to the user).
    """

    def __init__(self) -> None:
        import lark_oapi as lark

        from app.config import get_settings

        settings = get_settings()
        self._client = (
            lark.Client.builder()
            .app_id(settings.FEISHU_APP_ID)
            .app_secret(settings.FEISHU_APP_SECRET)
            .build()
        )

    async def get_events_around(
        self,
        user_id: str,
        date_hint: str,
        db: AsyncSession,
        max_events: int = 5,
    ) -> list[CalendarEvent]:
        """Return upcoming calendar events for *user_id* around *date_hint*.

        Raises CalendarFetchError when the user has not authorized calendar
        access or the token cannot be refreshed — caller should then send the
        user an OAuth authorization link via get_auth_url().
        """
        from app.integrations.feishu.oauth import get_valid_token

        user_token = await get_valid_token(user_id, db)
        if not user_token:
            raise CalendarFetchError(f"user {user_id} 未完成飞书日历授权")

        start_ts, end_ts = _resolve_date_range(date_hint)

        # Step 1: get the user's primary calendar ID using user token
        try:
            import lark_oapi as lark
            from lark_oapi.api.calendar.v4 import ListCalendarRequest

            option = lark.RequestOption.builder().user_access_token(user_token).build()
            cal_req = ListCalendarRequest.builder().build()
            cal_resp = await asyncio.to_thread(
                self._client.calendar.v4.calendar.list, cal_req, option
            )
        except Exception as exc:
            raise CalendarFetchError(f"calendar list API error: {exc}") from exc

        if not cal_resp.success():
            import contextlib

            raw_body = ""
            with contextlib.suppress(Exception):
                raw_body = (
                    cal_resp.raw.content.decode("utf-8", errors="replace")[:500]
                    if cal_resp.raw and cal_resp.raw.content
                    else ""
                )
            raise CalendarFetchError(
                f"calendar list API error code {cal_resp.code}: {cal_resp.msg}"
                + (f" / raw={raw_body}" if raw_body else "")
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

            # Feishu requires page_size >= 50; we still slice to max_events below.
            req = (
                ListCalendarEventRequest.builder()
                .calendar_id(calendar_id)
                .start_time(start_ts)
                .end_time(end_ts)
                .page_size(max(50, max_events))
                .build()
            )
            resp = await asyncio.to_thread(
                self._client.calendar.v4.calendar_event.list, req, option
            )
        except Exception as exc:
            raise CalendarFetchError(f"calendar API error: {exc}") from exc

        if not resp.success():
            import contextlib

            raw_body = ""
            with contextlib.suppress(Exception):
                raw_body = (
                    resp.raw.content.decode("utf-8", errors="replace")[:500]
                    if resp.raw and resp.raw.content
                    else ""
                )
            raise CalendarFetchError(
                f"calendar API returned error code {resp.code}: {resp.msg}"
                + (f" / raw={raw_body}" if raw_body else "")
            )

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
