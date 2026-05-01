"""PPT content generation prompts — per page_type branches."""

from __future__ import annotations

# These are NOT registered as PromptVersion objects because they are
# called directly (not via the versioning registry).  The registry is
# for nodes that get a single LLM call; ppt_content_gen dispatches
# per-slide to a different template per page_type.

COVER_PROMPT = """\
你是 Forge PPT 内容生成助手。请为封面幻灯片生成内容。

## 幻灯片信息
- 标题：{title}
- 演讲者备注草稿：{speaker_notes}
- 整份 PPT 主题：{ppt_title}
- 目标受众：{target_audience}

## 规则
- 封面只有主标题和可选副标题（不超过 20 字）
- 不需要 bullet_points
- 演讲者备注 ≤100 字

## 输出格式（JSON）
{{"heading": "主标题", "subheading": "副标题（可空）", "speaker_notes": "演讲者备注"}}
"""

AGENDA_PROMPT = """\
你是 Forge PPT 内容生成助手。请为目录/议程幻灯片生成内容。

## 幻灯片信息
- 标题：{title}
- 要点草稿：{bullet_points}
- 整份 PPT 结构：{slide_titles_summary}

## 规则
- 列出 3-6 个议程项，每项 ≤20 字
- 演讲者备注 ≤80 字

## 输出格式（JSON）
{{"heading": "目录标题", "items": ["议程1", "议程2"], "speaker_notes": "备注"}}
"""

SECTION_HEADER_PROMPT = """\
你是 Forge PPT 内容生成助手。请为章节分隔页生成内容。

## 幻灯片信息
- 章节标题：{title}
- 所属 PPT 主题：{ppt_title}

## 规则
- 只有大标题，加一句 ≤30 字的引导语
- 不需要 bullet_points

## 输出格式（JSON）
{{"heading": "章节大标题", "tagline": "引导语", "speaker_notes": ""}}
"""

CONTENT_PROMPT = """\
你是 Forge PPT 内容生成助手。请为内容页生成完整幻灯片文字。

## 幻灯片信息
- 标题：{title}
- 要点草稿（来自大纲）：{bullet_points}
- 演讲者备注草稿：{speaker_notes}
- 目标受众：{target_audience}

## 规则
- 扩写或精炼 bullet_points，保持 3-6 条，每条 ≤60 字
- 每条要点应有实质内容，避免空话
- 演讲者备注 ≤150 字，补充数据或上下文

## 输出格式（JSON）
{{"heading": "幻灯片标题", "bullets": ["要点1", "要点2", "要点3"], "speaker_notes": "备注"}}
"""

CLOSING_PROMPT = """\
你是 Forge PPT 内容生成助手。请为结束页生成内容。

## 幻灯片信息
- 标题：{title}
- 整份 PPT 主题：{ppt_title}
- 目标受众：{target_audience}

## 规则
- 结束页包含致谢/Q&A 提示，可选联系方式占位符
- 保持简洁，≤3 个元素

## 输出格式（JSON）
{{"heading": "结束标题", "subheading": "副标题或 Q&A 提示", "speaker_notes": ""}}
"""

PAGE_TYPE_PROMPTS: dict[str, str] = {
    "cover": COVER_PROMPT,
    "agenda": AGENDA_PROMPT,
    "section_header": SECTION_HEADER_PROMPT,
    "content": CONTENT_PROMPT,
    "closing": CLOSING_PROMPT,
}
