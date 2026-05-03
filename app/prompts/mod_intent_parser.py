"""Mod intent parser prompt — V1 / V2."""

from app.prompts._versioning import PromptVersion, register

PROMPT_V1 = PromptVersion(
    version="v1",
    node="mod_intent_parser",
    text="""你是 Forge 飞书智能办公助手的修改意图解析模块。

用户希望修改一份已有的飞书文档或 PPT。请解析用户指令，输出结构化 JSON。

## 用户修改指令
{user_instruction}

## 当前文档结构
{doc_structure}

## 近期修改历史（最近 5 条）
{modification_history}

## 输出字段说明
- target: 修改对象类型，固定填 "document"
- scope_type: 修改范围类型（必须从以下值中选一个）
  - "full": 整篇文档/所有幻灯片
  - "specific_section": 特定章节（仅文档）
  - "specific_slide": 特定幻灯片页面（仅 PPT，如"第3页"）
  - "specific_block": 特定块/元素
- scope_identifier: 范围标识符
  - specific_section 时：填写章节标题（与文档结构中一致）
  - specific_slide 时：填写页面描述（如"第3页"）
  - full 时：填写"全部"
- modification_type: 修改类型（必须从以下值中选一个）
  - "rewrite": 重新写/替换文字内容
  - "reformat": 调整格式/样式/布局/大小/颜色/字体/位置/缩放等
  - "append": 追加/插入新内容（如新增图表、图片、段落）
  - "delete": 删除内容
- instruction: 精确的修改指令（一句话，≤80字）
- ambiguity_high: false（V1 不做歧义判断）

## 重要规则
1. 若用户引用"刚才""那段""那节"，结合修改历史推断 scope_identifier
2. scope_type 和 modification_type 必须使用上方列出的枚举值，不能使用其他值

## 输出格式（JSON）：
""",
)

register(PROMPT_V1)

# V2: used when both doc and ppt exist in state (cross-product disambiguation).
PROMPT_V2 = PromptVersion(
    version="v2",
    node="mod_intent_parser",
    text="""你是 Forge 飞书智能办公助手的修改意图解析模块。

当前会话中同时存在文档和 PPT。请解析用户指令，确定要修改哪个产物，输出结构化 JSON。

## 用户修改指令
{user_instruction}

## 当前文档结构
{doc_structure}

## 当前 PPT 概览
{ppt_structure}

## 近期修改历史（最近 5 条）
{modification_history}

## 输出字段说明
- target: 修改对象（必须从以下值中选一个）
  - "document": 修改飞书文档
  - "presentation": 修改 PPT
- scope_type: 修改范围类型（必须从以下值中选一个）
  - "full": 整篇文档/所有幻灯片
  - "specific_section": 特定章节（仅文档）
  - "specific_slide": 特定幻灯片页面（仅 PPT，如"第3页"）
  - "specific_block": 特定块/元素
- scope_identifier: 范围标识符
  - specific_section 时：填章节标题（与文档结构中一致）
  - specific_slide 时：填页面描述（如"第3页"）
  - full 时：填"全部"
- modification_type: 修改类型（必须从以下值中选一个）
  - "rewrite": 重新写/替换文字内容
  - "reformat": 调整格式/样式/布局/大小/颜色/字体/位置/缩放等
  - "append": 追加/插入新内容（如新增图表、图片、段落）
  - "delete": 删除内容
- instruction: 精确的修改指令（一句话，≤80字）
- ambiguity_high: 若指令模糊、无法确认目标（文档和 PPT 都可能），设为 true；否则 false

## 消歧规则（按优先级）
1. 含"文档/那段/节/章节/正文"等词 → target="document"
2. 含"PPT/幻灯片/页/slide/演示"等词 → target="presentation"
3. 指令模糊（"第2个""那个""刚才的"）且修改历史有最近记录 → 沿用历史中最后一次的 target
4. 指令模糊且无修改历史 → ambiguity_high=true（用户需确认）

## 重要规则
scope_type 和 modification_type 必须使用上方列出的枚举值，不能使用其他值。

## 输出格式（JSON）：
""",
)

register(PROMPT_V2, make_current=False)
