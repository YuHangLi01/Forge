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
    "prior_artifact_retrieval": "检索历史产物",
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
    goal: str | None = None,
    notes_preview: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Card showing the execution plan with Confirm / Replan / Cancel buttons."""
    lines = []
    for i, step in enumerate(steps, 1):
        node = str(step.get("node_name", "?"))
        label = _NODE_LABELS.get(node, node)
        secs = step.get("estimated_seconds", 0)
        lines.append(f"{i}. {label}（约 {secs} 秒）")
    steps_md = "\n".join(lines)

    parts: list[str] = []
    if goal:
        parts.append(f"**🎯 目标：** {goal}")
    parts.append(f"**⏱️ 预计耗时：** 约 {total_seconds} 秒")
    if notes_preview:
        parts.append(f"\n📚 我从你的笔记里翻出了 **{len(notes_preview)} 条**相关记录：")
        for n in notes_preview:
            ts = n.get("ts", "")
            snippet = n.get("snippet", "")
            parts.append(f"> {ts} 你记下：「{snippet}…」")
    parts.append(f"\n📋 **执行计划（{len(steps)} 步）**\n{steps_md}")
    body_md = "\n".join(parts)

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "wathet",
            "title": {"tag": "plain_text", "content": "执行计划预览"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": body_md,
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
                    f"我看到你的指令可能针对文档或 PPT。请确认「{scope_identifier}」是指哪个？"
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


def battle_report_card(
    *,
    doc_url: str | None = None,
    doc_title: str | None = None,
    ppt_url: str | None = None,
    ppt_title: str | None = None,
    is_partial: bool = False,
    mention_user_ids: list[str] | None = None,
    wiki_url: str | None = None,
    notes_used_count: int = 0,
    notes_summary: str = "",
    replan_count: int = 0,
    elapsed_seconds: int = 0,
) -> dict[str, object]:
    """Consolidated delivery card shown after all artifacts are generated."""
    header_template = "orange" if is_partial else "green"
    header_text = "任务部分完成" if is_partial else "🎉 任务完成"

    lines: list[str] = []

    # @mention relevant contributors (Feishu markdown `<at user_id="...">` syntax)
    if mention_user_ids:
        at_line = " ".join(f'<at user_id="{uid}"></at>' for uid in mention_user_ids)
        lines.append(at_line)
        lines.append("")

    if doc_url:
        label = doc_title or "飞书文档"
        lines.append(f"📄 [{label}]({doc_url})")
    if ppt_url:
        label = ppt_title or "演示文稿"
        lines.append(f"📊 [{label}]({ppt_url})")
    if wiki_url:
        lines.append(f"📂 [知识库归档]({wiki_url})")

    if notes_used_count or replan_count or elapsed_seconds:
        lines.append("")  # blank line separator
    if notes_used_count:
        suffix = f"：{notes_summary}" if notes_summary else ""
        lines.append(f"💭 我引用了你 **{notes_used_count} 条**笔记{suffix}")
    if replan_count:
        lines.append(f"🔧 期间我自主决策：{replan_count} 次 replan")
    if elapsed_seconds:
        lines.append(f"⏱️ 总耗时：{elapsed_seconds} 秒")

    content = "\n".join(lines) if lines else "无可用产出物"
    if is_partial:
        content += "\n\n> ⚠️ 部分步骤未能完成，以上为已生成内容。"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": header_template,
            "title": {"tag": "plain_text", "content": header_text},
        },
        "elements": [
            {"tag": "markdown", "content": content},
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


def tool_use_card(
    tool_name: str,
    input_summary: str,
    output_summary: str = "",
) -> dict[str, object]:
    """Progress card showing an in-flight tool call (visible Agent self-awareness)."""
    body = f"🔧 **调用工具：{tool_name}**\n\n**输入：** {input_summary}"
    if output_summary:
        body += f"\n\n**返回：** {output_summary}"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "Agent 正在调用工具"},
        },
        "elements": [{"tag": "markdown", "content": body}],
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


def prior_artifact_confirm_card(
    *,
    title: str,
    share_url: str,
    slide_count: int,
    task_id: str,
    message_id: str,
) -> dict[str, object]:
    """Confirmation card shown when a previously-delivered artifact is found in ChromaDB."""
    subtitle = f"📊 {slide_count} 页 · {title}"
    return {
        "type": "card",
        "body": {
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"我找到了你之前完成的任务产物：\n\n**{title}**\n\n{subtitle}"
                            + (f"\n[打开产物]({share_url})" if share_url else "")
                            + "\n\n你说的是这个吗？"
                        ),
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "✅ 是的"},
                            "type": "primary",
                            "value": {
                                "action": "confirm_prior_artifact",
                                "task_id": task_id,
                                "thread_id": message_id,
                            },
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔄 不是，我说的是另一份"},
                            "type": "default",
                            "value": {
                                "action": "deny_prior_artifact",
                                "thread_id": message_id,
                            },
                        },
                    ],
                },
            ]
        },
        "header": {
            "title": {"content": "找到历史产物", "tag": "plain_text"},
            "template": "turquoise",
        },
    }
