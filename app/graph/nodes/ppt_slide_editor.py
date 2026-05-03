"""ppt_slide_editor node: regenerate one slide, re-render .pptx, re-upload."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.graph.nodes._decorator import graph_node
from app.schemas.artifacts import ChartSchema, ChartSeries, SlideSchema
from app.schemas.enums import TaskStatus

_CHART_TRIGGER_RE = re.compile(
    r"图表|柱状图|折线图|饼图|bar\s*chart|line\s*chart|pie\s*chart|chart",
    re.IGNORECASE,
)

_RESIZE_TRIGGER_RE = re.compile(
    r"改小|缩小|变小|小一[点些]?|改大|放大|变大|大一[点些]?|resize|shrink|enlarge",
    re.IGNORECASE,
)

_CHART_MIN_W = 2.0
_CHART_MIN_H = 1.0
_CHART_MAX_W = 9.3
_CHART_MAX_H = 4.3

_CHART_EXTRACT_PROMPT = """\
请从以下修改指令中提取图表数据，输出 JSON。

修改指令：{instruction}

输出格式（严格 JSON，不加 markdown 代码块）：
{{
  "chart_type": "bar|line|pie",
  "title": "图表标题",
  "categories": ["类目1", "类目2"],
  "series": [
    {{"name": "系列名", "values": [数值1, 数值2]}}
  ]
}}

规则：
- chart_type 只能是 bar / line / pie
- categories 和 values 长度必须相同
- 如果指令中没有明确数据，编造合理的示例数据
- 只输出 JSON，不加任何解释
"""

logger = structlog.get_logger(__name__)

_CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_SLIDE_EDIT_PROMPT = """\
你是 Forge PPT 编辑助手。请根据修改指令修改幻灯片内容。

## 当前幻灯片
- 标题：{heading}
- 要点：
{bullets}
- 演讲者备注：{notes}

## 修改指令
{instruction}

## 规则
- 保留幻灯片结构，只修改文字内容
- bullets 保持 3-6 条，每条 ≤60 字（封面/结束页可为空列表）
- 演讲者备注 ≤150 字

## 输出格式（JSON）
{{"heading": "修改后标题", "bullets": ["要点1", "要点2"], "speaker_notes": "备注"}}
"""


def _extract_resize_scale(instruction: str) -> float | None:
    """Return a scale factor if instruction is a chart-resize request, else None.

    Examples: "改小一点" → 0.75, "缩小30%" → 0.70, "放大到150%" → 1.50
    """
    if not _RESIZE_TRIGGER_RE.search(instruction):
        return None

    lower = instruction.lower()
    is_shrink = any(k in lower for k in ("小", "缩", "shrink"))

    # "缩小到N%" / "放大到N%"
    m = re.search(r"(?:缩小到|放大到)\s*(\d+)\s*%", lower)
    if m:
        return int(m.group(1)) / 100

    # "缩小N%" / "放大N%"
    m = re.search(r"缩小\s*(\d+)\s*%", lower)
    if m:
        return 1.0 - int(m.group(1)) / 100
    m = re.search(r"放大\s*(\d+)\s*%", lower)
    if m:
        return 1.0 + int(m.group(1)) / 100

    # "放大一倍"
    if "一倍" in lower:
        return 0.5 if is_shrink else 2.0

    # "很多" / "大幅" / "明显" → aggressive
    if any(k in lower for k in ("很多", "大幅", "明显", "非常")):
        return 0.5 if is_shrink else 1.6

    # "一点" / "一些" / "稍" / "略" → gentle
    if any(k in lower for k in ("一点", "一些", "稍微", "稍", "略")):
        return 0.75 if is_shrink else 1.25

    # default: moderate
    return 0.7 if is_shrink else 1.3


def _parse_slide_index(scope_identifier: str) -> int:
    """Return 0-based index from '第2页' (→1) or '第三页' (→2). Defaults to 0."""
    m = re.search(r"\d+", scope_identifier)
    if m:
        return int(m.group()) - 1
    for cn, n in _CHINESE_DIGITS.items():
        if cn in scope_identifier:
            return n - 1
    return 0


@graph_node("ppt_slide_editor")
async def ppt_slide_editor_node(state: dict[str, Any]) -> dict[str, Any]:
    import redis.asyncio as aioredis

    from app.config import get_settings
    from app.integrations.feishu.adapter import FeishuAdapter
    from app.schemas.modification import ModificationRecord
    from app.services.llm_service import LLMService
    from app.services.ppt_service import PPTService
    from app.services.progress_broadcaster import ProgressBroadcaster

    message_id: str = state.get("message_id", "")
    chat_id: str = state.get("chat_id", "")

    ppt_artifact = state.get("ppt")
    if not ppt_artifact:
        return {"error": "没有可编辑的 PPT", "status": TaskStatus.failed}

    mod_intent = state.get("mod_intent")
    if not mod_intent:
        return {"error": "缺少修改意图", "status": TaskStatus.failed}

    scope_identifier: str = getattr(mod_intent, "scope_identifier", "第1页")
    scope_type: str = getattr(mod_intent, "scope_type", "specific_slide")
    if scope_type not in ("specific_slide",):
        return {
            "error": (
                f"PPT 修改仅支持指定具体页面，不支持范围「{scope_identifier}」，请说明要修改第几页"
            ),
            "status": TaskStatus.failed,
        }
    instruction: str = getattr(mod_intent, "instruction", "")
    if not instruction.strip():
        return {"error": "修改指令为空", "status": TaskStatus.failed}

    target_idx = _parse_slide_index(scope_identifier)

    slides: list[SlideSchema] = list(ppt_artifact.slides)
    if not slides:
        return {"error": "PPT 中没有幻灯片", "status": TaskStatus.failed}

    target_idx = max(0, min(target_idx, len(slides) - 1))
    target_slide = slides[target_idx]

    llm = LLMService()

    # Determine chart for the new slide:
    # 1. Resize: scale existing chart dimensions (no LLM call for text either)
    # 2. Add/replace chart: extract new chart data via LLM
    # 3. Otherwise: preserve whatever chart was already on the slide
    chart_schema: ChartSchema | None = target_slide.chart  # preserve by default
    resize_scale = _extract_resize_scale(instruction)

    # For pure chart resize, preserve original text — no LLM text edit needed.
    # (Calling the LLM with a layout instruction causes it to inject unwanted
    # commentary like "（已向下移动至合适位置）" into the slide bullets.)
    if resize_scale is not None:
        updated: dict[str, Any] = {
            "heading": target_slide.title,
            "bullets": list(target_slide.bullets),
            "speaker_notes": target_slide.speaker_notes or "",
        }
    else:
        bullets_text = "\n".join(f"- {b}" for b in target_slide.bullets) or "（无要点）"
        prompt = _SLIDE_EDIT_PROMPT.format(
            heading=target_slide.title,
            bullets=bullets_text,
            notes=target_slide.speaker_notes or "",
            instruction=instruction,
        )
        try:
            raw: str = await llm.invoke(prompt, tier="lite")
            stripped = raw.strip()
            if stripped.startswith("```"):
                lines = stripped.split("\n")
                stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            updated = json.loads(stripped)
        except Exception:
            logger.exception("ppt_slide_editor_llm_failed", slide_index=target_idx)
            return {"error": "幻灯片内容生成失败，请重试", "status": TaskStatus.failed}

    if resize_scale is not None and target_slide.chart is not None:
        old = target_slide.chart
        new_w = max(_CHART_MIN_W, min(old.width_inches * resize_scale, _CHART_MAX_W))
        new_h = max(_CHART_MIN_H, min(old.height_inches * resize_scale, _CHART_MAX_H))
        chart_schema = ChartSchema(
            chart_type=old.chart_type,
            title=old.title,
            categories=list(old.categories),
            series=list(old.series),
            width_inches=round(new_w, 2),
            height_inches=round(new_h, 2),
        )
        logger.info(
            "ppt_chart_resized",
            slide_index=target_idx,
            scale=resize_scale,
            w=chart_schema.width_inches,
            h=chart_schema.height_inches,
        )
    elif resize_scale is None and _CHART_TRIGGER_RE.search(instruction):
        try:
            chart_prompt = _CHART_EXTRACT_PROMPT.format(instruction=instruction)
            chart_raw: str = await llm.invoke(chart_prompt, tier="lite")
            stripped_chart = chart_raw.strip()
            if stripped_chart.startswith("```"):
                lines = stripped_chart.split("\n")
                stripped_chart = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            chart_dict: dict[str, Any] = json.loads(stripped_chart)
            chart_schema = ChartSchema(
                chart_type=chart_dict.get("chart_type", "bar"),
                title=chart_dict.get("title", ""),
                categories=chart_dict.get("categories", []),
                series=[
                    ChartSeries(name=s["name"], values=s["values"])
                    for s in chart_dict.get("series", [])
                ],
            )
        except Exception:
            logger.exception("ppt_slide_editor_chart_extract_failed", slide_index=target_idx)

    new_slide = SlideSchema(
        page_index=target_slide.page_index,
        layout=target_slide.layout,
        title=updated.get("heading", target_slide.title),
        bullets=updated.get("bullets") or [],
        speaker_notes=updated.get("speaker_notes", ""),
        visual_hint=target_slide.visual_hint,
        element_ids=target_slide.element_ids,
        chart=chart_schema,
    )
    slides[target_idx] = new_slide

    adapter = FeishuAdapter()
    svc = PPTService(adapter=adapter)
    new_artifact = await svc.create_from_outline(ppt_artifact.title, slides)

    pb = ProgressBroadcaster(message_id=message_id, thread_id=message_id)
    label = f"✅ 已修改「{scope_identifier}」"
    if new_artifact.share_url:
        pb.emit_artifact(label=label, url=new_artifact.share_url)

    history: list[Any] = list(state.get("modification_history") or [])
    mod_record = ModificationRecord(
        step_index=len(history),
        scope_identifier=scope_identifier,
        instruction=instruction,
        before_summary=target_slide.title[:200],
        after_summary=new_slide.title[:200],
        target="presentation",
    )

    if chat_id and new_artifact.ppt_id:
        try:
            settings = get_settings()
            async with aioredis.from_url(settings.REDIS_URL) as r:  # type: ignore[no-untyped-call]
                await r.setex(f"active_ppt:{chat_id}", 3600, new_artifact.model_dump_json())
        except Exception:
            logger.exception("ppt_slide_editor_cache_failed", chat_id=chat_id)

    logger.info("ppt_slide_editor_done", slide_index=target_idx, ppt_id=new_artifact.ppt_id)
    return {
        "ppt": new_artifact,
        "status": TaskStatus.completed,
        "completed_steps": ["ppt_slide_editor"],
        "modification_history": [mod_record],
    }
