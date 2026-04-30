"""Clarify question prompt — V1."""

from app.prompts._versioning import PromptVersion, register

PROMPT_V1 = PromptVersion(
    version="v1",
    node="clarify_question",
    text="""你是 Forge 飞书智能办公助手。用户的请求信息不足，无法直接执行任务。

请根据用户的原始消息，生成 **最多 2 个** 简洁的澄清问题，以便你能正确理解并完成任务。

要求：
1. 问题必须是封闭式或半封闭式的（有明确答案方向，不要问"请详细说明"）
2. 每个问题独立成行，不加编号
3. 优先问最关键的缺失信息（目的、受众、范围）
4. 如果有可供选择的选项，在问题后列出 2-3 个示例选项（括号内）
5. 只输出问题列表，不要有任何前缀或解释

用户消息：
{user_message}

已知意图摘要（如有）：
{intent_summary}

输出格式（纯文本，每行一个问题）：
""",
)

register(PROMPT_V1)
