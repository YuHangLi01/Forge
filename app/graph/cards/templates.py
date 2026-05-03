"""Pure-function Feishu interactive card templates.

All functions return a dict that can be passed directly to
``FeishuAdapter.update_card`` or sent as the card payload in a new message.
"""

from __future__ import annotations

_NODE_LABELS: dict[str, str] = {
    "preprocess": "理解输入内容",
    "intent_parser": "分析任务意图",
    "planner": "制定执行计划",
    "doc_structure_gen": "生成文档大纲",
    "doc_content_gen": "撰写文档内容",
    "feishu_doc_write": "写入飞书文档",
    "doc_section_editor": "修改文档章节",
    "mod_intent_parser": "解析修改意图",
    "ppt_structure_gen": "生成 PPT 大纲",
    "ppt_content_gen": "生成幻灯片内容",
    "feishu_ppt_write": "上传 PPT 至云盘",
    "ppt_slide_editor": "修改指定幻灯片",
    "scenario_composer": "分析生成场景",
    "lego_orchestrator": "编排多场景任务",
    "checkpoint_control": "执行检查点控制",
    "clarify_resume": "处理用户补充信息",
    "error_handler": "处理错误",
}


def clarify_card(questions: list[str]) -> dict[str, object]:
    """Card that shows clarifying questions and asks the user to reply in chat.

    Feishu card 2.0 form/input schemas are version-unstable and have caused
    repeated parse errors (200621, 300123, 11310). The reliable approach is to
    display the questions and have the user reply as a normal chat message;
    message_tasks intercepts the next message as the clarify answer.
    """
    questions_md = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions[:2]))
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "需要补充一些信息"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"为了更好地完成任务，请回答以下问题：\n\n{questions_md}"
                    "\n\n**请直接在聊天框输入您的回答后发送。**"
                ),
            },
        ],
    }


def plan_preview_card(
    steps: list[dict[str, object]],
    thread_id: str,
    total_seconds: int,
) -> dict[str, object]:
    """Card showing the execution plan with Confirm / Replan / Cancel buttons."""
    lines = []
    for i, step in enumerate(steps, 1):
        node = str(step.get("node_name", "?"))
        label = _NODE_LABELS.get(node, node)
        secs = step.get("estimated_seconds", 0)
        lines.append(f"{i}. {label}（约 {secs} 秒）")
    steps_md = "\n".join(lines)
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "wathet",
            "title": {"tag": "plain_text", "content": "执行计划预览"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**预计步骤：**\n{steps_md}\n\n**总耗时预估：** 约 {total_seconds} 秒"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认执行"},
                        "type": "primary",
                        "value": {
                            "action": "plan_confirm",
                            "thread_id": thread_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "重新规划"},
                        "type": "default",
                        "value": {
                            "action": "plan_replan",
                            "thread_id": thread_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "取消"},
                        "type": "danger",
                        "value": {
                            "action": "plan_cancel",
                            "thread_id": thread_id,
                        },
                    },
                ],
            },
        ],
    }


def doc_done_card(label: str, url: str) -> dict[str, object]:
    """Card shown when a document has been successfully written to Feishu."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "green",
            "title": {"tag": "plain_text", "content": "文档已生成"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"**{label}**\n\n[点击查看文档]({url})",
            },
        ],
    }


def timeout_card(thread_id: str) -> dict[str, object]:
    """Card shown when a Celery task times out mid-execution."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "思考超时"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "当前任务处理时间较长，已超过单次限制。\n是否继续尝试？",
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "继续"},
                        "type": "primary",
                        "value": {"action": "task_continue", "thread_id": thread_id},
                    }
                ],
            },
        ],
    }


def mod_target_clarify_card(
    scope_identifier: str,
    thread_id: str,
) -> dict[str, object]:
    """Card asking user to confirm which artifact to modify (doc, ppt, or both)."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "请确认修改目标"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"我看到你的指令可能针对文档或 PPT。" f"请确认「{scope_identifier}」是指哪个？"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": f"📄 文档{scope_identifier}"},
                        "type": "primary",
                        "value": {
                            "action": "mod_target",
                            "target": "document",
                            "thread_id": thread_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": f"📊 PPT{scope_identifier}"},
                        "type": "default",
                        "value": {
                            "action": "mod_target",
                            "target": "presentation",
                            "thread_id": thread_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📄+📊 都改"},
                        "type": "default",
                        "value": {
                            "action": "mod_target",
                            "target": "both",
                            "thread_id": thread_id,
                        },
                    },
                ],
            },
        ],
    }


def error_card(message: str) -> dict[str, object]:
    """Simple error notification card."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": "任务失败"},
        },
        "elements": [
            {"tag": "markdown", "content": f"**错误信息：** {message}"},
        ],
    }


def calendar_clarify_card(
    events: list[dict[str, str]],
    thread_id: str,
) -> dict[str, object]:
    """Card showing calendar events as buttons for the user to select.

    Each event dict has keys: summary, start_time, end_time.
    """
    buttons = []
    for evt in events[:5]:
        summary = evt.get("summary", "(无标题)")
        start = evt.get("start_time", "")
        label = f"📅 {summary}" + (f"  {start}" if start else "")
        buttons.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": label},
                "type": "default",
                "value": {
                    "action": "clarify_submit",
                    "thread_id": thread_id,
                    "request_id": thread_id,
                    "clarify_answer": summary,
                },
            }
        )
    buttons.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "其他（自行输入）"},
            "type": "default",
            "value": {
                "action": "clarify_submit",
                "thread_id": thread_id,
                "request_id": thread_id,
                "clarify_answer": "其他",
            },
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "请选择是哪个日程"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "我看到明天有以下日程，请选择您要准备的是哪一个：",
            },
            {"tag": "action", "actions": buttons},
        ],
    }


def lego_scenario_select_card(thread_id: str, chat_id: str) -> dict[str, object]:
    """Card for selecting Lego scenario combination (C=doc, D=PPT)."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "🧱 Lego 场景组合器"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": "**请选择要执行的场景组合：**\n点击后请在对话框输入您的需求。",
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📄 C 文档 + 📊 D PPT"},
                        "type": "primary",
                        "value": {
                            "action": "lego_start",
                            "scenarios": ["C", "D"],
                            "thread_id": thread_id,
                            "chat_id": chat_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📄 仅文档"},
                        "type": "default",
                        "value": {
                            "action": "lego_start",
                            "scenarios": ["C"],
                            "thread_id": thread_id,
                            "chat_id": chat_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📊 仅 PPT"},
                        "type": "default",
                        "value": {
                            "action": "lego_start",
                            "scenarios": ["D"],
                            "thread_id": thread_id,
                            "chat_id": chat_id,
                        },
                    },
                ],
            },
        ],
    }
