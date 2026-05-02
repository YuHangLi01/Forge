"""Node name → user-friendly progress text templates.

Used by ProgressBroadcaster.begin_node / end_node so that progress cards
show natural Chinese text instead of raw node identifiers.
"""

from __future__ import annotations

BEFORE_TEMPLATES: dict[str, str] = {
    "preprocess": "正在理解您的输入…",
    "intent_parser": "正在分析任务意图…",
    "context_retrieval": "正在检索背景资料…",
    "planner": "正在制定执行计划…",
    "doc_structure_gen": "正在生成文档大纲…",
    "doc_content_gen": "正在生成文档内容…",
    "feishu_doc_write": "正在写入飞书文档…",
    "mod_intent_parser": "正在解析修改意图…",
    "doc_section_editor": "正在修改文档章节…",
    "ppt_structure_gen": "正在生成 PPT 大纲…",
    "ppt_content_gen": "正在生成幻灯片内容…",
    "feishu_ppt_write": "正在上传 PPT 到云盘…",
    "ppt_slide_editor": "正在修改幻灯片…",
    "clarify_question": "正在生成澄清问题…",
    "clarify_resume": "正在继续处理您的回答…",
    "scenario_composer": "正在组合任务场景…",
    "lego_orchestrator": "正在编排执行计划…",
    "checkpoint_control": "任务已暂停，等待您的确认…",
    "step_router": "正在规划下一步…",
    "error_handler": "正在处理异常情况…",
}

AFTER_TEMPLATES: dict[str, str] = {
    "preprocess": "输入已理解",
    "intent_parser": "意图分析完成",
    "context_retrieval": "背景资料检索完成",
    "planner": "执行计划已制定",
    "doc_structure_gen": "文档大纲已生成",
    "doc_content_gen": "文档内容已生成",
    "feishu_doc_write": "飞书文档已写入",
    "mod_intent_parser": "修改意图已解析",
    "doc_section_editor": "文档章节已修改",
    "ppt_structure_gen": "PPT 大纲已生成",
    "ppt_content_gen": "幻灯片内容已生成",
    "feishu_ppt_write": "PPT 已上传至云盘",
    "ppt_slide_editor": "幻灯片已修改",
    "clarify_question": "澄清问题已发送",
    "clarify_resume": "已收到您的回答",
    "scenario_composer": "任务场景已确定",
    "lego_orchestrator": "执行计划已编排",
    "checkpoint_control": "任务已暂停",
    "step_router": "路由决策完成",
    "error_handler": "异常已处理",
}

_DEFAULT_BEFORE = "正在处理…"
_DEFAULT_AFTER = "已完成"


def get_before_text(node_name: str) -> str:
    """Return the user-facing 'in progress' text for *node_name*."""
    return BEFORE_TEMPLATES.get(node_name, _DEFAULT_BEFORE)


def get_after_text(node_name: str) -> str:
    """Return the user-facing 'done' text for *node_name*."""
    return AFTER_TEMPLATES.get(node_name, _DEFAULT_AFTER)
