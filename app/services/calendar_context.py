"""Calendar context utilities for intent disambiguation."""

from __future__ import annotations

import re

from app.integrations.feishu.calendar import CalendarEvent

_TIME_WORD_RE = re.compile(
    r"(今天|明天|后天|下周|本周|上午|下午|晚上|早上|"
    r"周一|周二|周三|周四|周五|周六|周日|"
    r"星期一|星期二|星期三|星期四|星期五|星期六|星期日|"
    r"\d{1,2}[点时]|\d{4}-\d{2}-\d{2})"
)


def has_time_word(text: str) -> bool:
    """Return True if *text* contains a recognisable time/date reference."""
    return bool(_TIME_WORD_RE.search(text))


def format_events_for_prompt(events: list[CalendarEvent]) -> str:
    """Format calendar events as a concise LLM-readable block.

    Only exposes event titles and time strings — no attendees or descriptions.
    """
    if not events:
        return ""
    lines = ["相关日程（供参考）："]
    for ev in events:
        time_part = f"{ev.start_time} – {ev.end_time}" if ev.start_time else "(时间未知)"
        lines.append(f"- {ev.summary}（{time_part}）")
    return "\n".join(lines)
