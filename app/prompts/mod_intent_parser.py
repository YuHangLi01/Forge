"""Mod intent parser prompt — V1."""

from app.prompts._versioning import PromptVersion, register

PROMPT_V1 = PromptVersion(
    version="v1",
    node="mod_intent_parser",
    text="""你是 Forge 飞书智能办公助手的修改意图解析模块。

用户希望修改一份已有的飞书文档。请解析用户指令，输出结构化 JSON。

## 用户修改指令
{user_instruction}

## 当前文档结构
{doc_structure}

## 近期修改历史（最近 5 条）
{modification_history}

## 输出字段说明
- target: 修改对象类型，固定填 "document"
- scope_type: 修改范围类型
  - "full": 整篇文档
  - "specific_section": 特定章节
- scope_identifier: 范围标识符
  - specific_section 时：填写章节标题（与文档结构中一致）
  - full 时：填写文档 doc_id
- modification_type: 修改类型
  - "rewrite": 重新写
  - "reformat": 调整格式
  - "append": 追加内容
  - "delete": 删除内容
- instruction: 精确的修改指令（一句话，≤80字）

## 重要规则
1. 若用户引用"刚才""那段""那节"，结合修改历史推断 scope_identifier
2. scope_identifier 必须是文档中实际存在的章节标题

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
- target: 修改对象
  - "document": 修改飞书文档
  - "presentation": 修改 PPT
- scope_type / scope_identifier / modification_type / instruction: 同 V1
- ambiguity_high: 若指令模糊、无法确认目标（两者都可能），设为 true；否则 false

## 消歧规则（按优先级）
1. 含"文档/那段/节/章节/正文"等词 → target="document"
2. 含"PPT/幻灯片/页/slide/演示"等词 → target="presentation"
3. 指令模糊（"第2个""那个""刚才的"）且修改历史有最近记录 → 沿用历史中最后一次的 target
4. 指令模糊且无修改历史 → ambiguity_high=true（用户需确认）

## 输出格式（JSON）：
""",
)

register(PROMPT_V2, make_current=False)
