"""Pure-function Feishu interactive card templates.

All functions return a dict that can be passed directly to
``FeishuAdapter.update_card`` or sent as the card payload in a new message.
"""

from __future__ import annotations


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
        node = step.get("node_name", "?")
        secs = step.get("estimated_seconds", 0)
        lines.append(f"{i}. `{node}` (~{secs}s)")
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
