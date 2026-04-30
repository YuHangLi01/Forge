"""Pure-function Feishu interactive card templates.

All functions return a dict that can be passed directly to
``FeishuAdapter.update_card`` or sent as the card payload in a new message.
"""

from __future__ import annotations


def clarify_card(questions: list[str], request_id: str, thread_id: str) -> dict[str, object]:
    """Card that asks the user ≤2 clarifying questions with a free-text input.

    The submit button value encodes request_id + thread_id so card_tasks can
    resume the correct graph thread.  The form element named "clarify_answer"
    carries whatever the user typed.
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
                "content": f"为了更好地完成任务，请回答以下问题：\n\n{questions_md}",
            },
            {
                "tag": "input",
                "placeholder": {"tag": "plain_text", "content": "请输入您的回答…"},
                "name": "clarify_answer",
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "提交回答"},
                        "type": "primary",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "action": "clarify_submit",
                                    "request_id": request_id,
                                    "thread_id": thread_id,
                                },
                            }
                        ],
                    }
                ],
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
                    f"**预计步骤：**\n{steps_md}\n\n" f"**总耗时预估：** 约 {total_seconds} 秒"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认执行"},
                        "type": "primary",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "action": "plan_confirm",
                                    "thread_id": thread_id,
                                },
                            }
                        ],
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "重新规划"},
                        "type": "default",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "action": "plan_replan",
                                    "thread_id": thread_id,
                                },
                            }
                        ],
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "取消"},
                        "type": "danger",
                        "behaviors": [
                            {
                                "type": "callback",
                                "value": {
                                    "action": "plan_cancel",
                                    "thread_id": thread_id,
                                },
                            }
                        ],
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
