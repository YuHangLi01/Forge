"""Feishu card templates for mid-execution pause and resume."""

from __future__ import annotations


def build_pause_card(
    completed_steps: list[str],
    pending_steps: list[str],
    thread_id: str,
) -> dict[str, object]:
    """Card shown when user pauses execution.

    Displays completed steps (with checkmark) and pending steps (grayed out),
    plus three action buttons: Resume, Edit Doc, Cancel.
    """
    completed_md = "\n".join(f"✅ {s}" for s in completed_steps) or "（无）"
    pending_md = "\n".join(f"⏸ {s}" for s in pending_steps) or "（无）"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "yellow",
            "title": {"tag": "plain_text", "content": "⏸ 执行已暂停"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**已完成步骤：**\n{completed_md}"
                    f"\n\n**待执行步骤：**\n{pending_md}"
                    "\n\n请选择后续操作："
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "▶️ 继续"},
                        "type": "primary",
                        "value": {"action": "checkpoint_resume", "thread_id": thread_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✏️ 修改文档"},
                        "type": "default",
                        "value": {"action": "checkpoint_edit_doc", "thread_id": thread_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 取消"},
                        "type": "danger",
                        "value": {"action": "checkpoint_cancel", "thread_id": thread_id},
                    },
                ],
            },
        ],
    }
