"""Planner prompt — V1."""

from app.prompts._versioning import PromptVersion, register

_AVAILABLE_NODES = """
可用节点（node_name 只能从以下选择）：
- doc_structure_gen   生成文档大纲（依赖：无）
- doc_content_gen     生成文档内容（依赖：doc_structure_gen）
- feishu_doc_write    写入飞书文档（依赖：doc_content_gen）
""".strip()

PROMPT_V1 = PromptVersion(
    version="v1",
    node="planner",
    text="""你是 Forge 飞书智能办公助手的规划模块。

根据用户意图，生成一个结构化执行计划（JSON）。

## 用户意图
- 主要目标：{primary_goal}
- 任务类型：{task_type}
- 期望输出：{output_formats}

## 检索到的背景资料摘要
{context_summary}

## 规则
1. 每个步骤必须有唯一 id（格式：step_1, step_2, ...）
2. node_name 必须从可用节点列表中选择，不得使用其他节点
3. depends_on 列出该步骤依赖的步骤 id 列表（空数组表示无依赖）
4. 只有最终输出步骤才能设 requires_human_confirm=true
5. total_estimated_seconds ≤ 150（总耗时约束）
6. 禁止循环依赖

## 可用节点
{available_nodes}

## 输出格式（JSON）
{{
  "steps": [
    {{"id": "step_1", "node_name": "doc_structure_gen",
      "depends_on": [], "requires_human_confirm": false, "estimated_seconds": 10}},
    {{"id": "step_2", "node_name": "doc_content_gen",
      "depends_on": ["step_1"], "requires_human_confirm": false, "estimated_seconds": 60}},
    {{"id": "step_3", "node_name": "feishu_doc_write",
      "depends_on": ["step_2"], "requires_human_confirm": false, "estimated_seconds": 5}}
  ],
  "total_estimated_seconds": 75
}}
""",
)

register(PROMPT_V1)

AVAILABLE_NODES = _AVAILABLE_NODES
