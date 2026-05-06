"""Doc structure prompt — V1."""

from app.prompts._versioning import PromptVersion, register

PROMPT_V1 = PromptVersion(
    version="v1",
    node="doc_structure_gen",
    text="""你是 Forge 飞书智能办公助手的文档结构规划模块。

根据以下信息，生成一份文档的结构大纲（JSON 格式）。

## 用户意图
- 主要目标：{primary_goal}
- 目标受众：{target_audience}
- 文档风格：{style_hint}

## 用户素材（可能含个人笔记/历史记录/已交付产物，请综合利用）
{context_summary}

注意：标记为 "demo_seed" 或 "conversation" 的条目是用户的原始笔记/对话片段，
不是已完成的报告。请把它们作为素材组织成正式材料，不要直接引用原文。

## 要求
1. sections 数量：3~6 个
2. 每个 section 的 id 格式：s0, s1, s2, ...
3. title 应简洁、有意义（≤15字）
4. document_title 应准确概括文档主题（≤20字）

## 输出格式（JSON）
{{
  "document_title": "文档标题",
  "sections": [
    {{"id": "s0", "title": "节标题 1"}},
    {{"id": "s1", "title": "节标题 2"}},
    {{"id": "s2", "title": "节标题 3"}}
  ]
}}
""",
)

register(PROMPT_V1)
