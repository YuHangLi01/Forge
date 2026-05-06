"""Feishu calendar integration — read-only event fetching for intent disambiguation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_BEIJING_TZ = timezone(timedelta(hours=8))


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
    """Convert a natural-language date hint to Unix timestamps (as strings).

    The window covers a full Beijing-time calendar day (00:00 — 24:00 CST),
    not a UTC day, because "今天/明天" in the user's mental model means the
    Beijing date. Returns (start_ts, end_ts) suitable for the Feishu API.
    """
    today = datetime.now(_BEIJING_TZ).date()
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

    start_dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_BEIJING_TZ)
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
        logger.info(
            "calendar_query_window",
            date_hint=date_hint,
            start_ts=start_ts,
            end_ts=end_ts,
            start_human=datetime.fromtimestamp(int(start_ts), _BEIJING_TZ).isoformat(),
            end_human=datetime.fromtimestamp(int(end_ts), _BEIJING_TZ).isoformat(),
        )

        # Bypass lark_oapi SDK and call Feishu API directly via httpx with an
        # explicit Bearer token. The SDK was observed to silently use the
        # tenant_access_token (app-level) even when user_access_token was set
        # on the RequestOption — which made /calendars return only the bot's
        # own internal calendar (summary="办公智能协同助手") instead of the
        # user's personal calendar (summary=user's name). curl with the same
        # token returned the user's calendar correctly, so plain httpx works.
        import httpx

        headers = {"Authorization": f"Bearer {user_token}"}
        base = "https://open.feishu.cn/open-apis/calendar/v4"

        try:
            async with httpx.AsyncClient(timeout=15) as http:
                cal_r = await http.get(
                    f"{base}/calendars",
                    headers=headers,
                    params={"page_size": 50},
                )
        except Exception as exc:
            raise CalendarFetchError(f"calendar list API error: {exc}") from exc

        cal_body = cal_r.json() if cal_r.content else {}
        if cal_body.get("code", -1) != 0:
            raise CalendarFetchError(
                f"calendar list API error code {cal_body.get('code')}: "
                f"{cal_body.get('msg')} / raw={str(cal_body)[:500]}"
            )

        calendars = (cal_body.get("data") or {}).get("calendar_list") or []
        # Strict filter: must be role=owner so the events endpoint will accept us.
        # Prefer type=primary among owned calendars.
        owned = [c for c in calendars if c.get("role") == "owner"]
        primary = next(
            (c for c in owned if c.get("type") == "primary"),
            owned[0] if owned else None,
        )
        calendar_id = primary.get("calendar_id") if primary else None

        if not calendar_id:
            raise CalendarFetchError("用户名下没有可访问的主日历（role=owner）")

        logger.info(
            "calendar_selected",
            calendar_id=calendar_id,
            total_calendars=len(calendars),
            owned_count=len(owned),
            primary_summary=primary.get("summary", "") if primary else "",
        )

        # Step 2: list events in the date range (page_size must be >= 50)
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                evt_r = await http.get(
                    f"{base}/calendars/{calendar_id}/events",
                    headers=headers,
                    params={
                        "start_time": start_ts,
                        "end_time": end_ts,
                        "page_size": max(50, max_events),
                    },
                )
        except Exception as exc:
            raise CalendarFetchError(f"calendar API error: {exc}") from exc

        evt_body = evt_r.json() if evt_r.content else {}
        if evt_body.get("code", -1) != 0:
            raise CalendarFetchError(
                f"calendar API returned error code {evt_body.get('code')}: "
                f"{evt_body.get('msg')} / raw={str(evt_body)[:500]}"
            )

        items = (evt_body.get("data") or {}).get("items") or []
        logger.info(
            "calendar_events_fetched",
            calendar_id=calendar_id,
            raw_items_count=len(items),
            window=f"{start_ts}->{end_ts}",
            sample_summaries=[it.get("summary", "") for it in items[:3]],
        )
        events: list[CalendarEvent] = []
        for item in items[:max_events]:
            events.append(
                CalendarEvent(
                    summary=item.get("summary") or "(无标题)",
                    start_time=(item.get("start_time") or {}).get("timestamp", ""),
                    end_time=(item.get("end_time") or {}).get("timestamp", ""),
                )
            )
        return events
