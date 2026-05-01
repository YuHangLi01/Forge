"""Stage-gated node whitelist.

FORGE_STAGE=2 → doc_* pipeline only.
FORGE_STAGE=3 → also unlocks ppt_* pipeline.
The planner receives only allowed nodes so it cannot schedule future-stage work.
"""

from __future__ import annotations

_STAGE_2_NODES: frozenset[str] = frozenset(
    [
        "doc_structure_gen",
        "doc_content_gen",
        "feishu_doc_write",
        "doc_section_editor",
        "mod_intent_parser",
    ]
)

_STAGE_3_EXTRA_NODES: frozenset[str] = frozenset(
    [
        "ppt_structure_gen",
        "ppt_content_gen",
        "feishu_ppt_write",
        "ppt_slide_editor",
    ]
)


def get_allowed_nodes(stage: int) -> frozenset[str]:
    """Return the set of pipeline nodes the planner may schedule for *stage*."""
    if stage >= 3:
        return _STAGE_2_NODES | _STAGE_3_EXTRA_NODES
    return _STAGE_2_NODES


def build_available_nodes_prompt(stage: int) -> str:
    """Return the 'Available Nodes' block for the planner prompt."""
    lines = [
        "可用节点（node_name 只能从以下选择）：",
        "- doc_structure_gen   生成文档大纲（依赖：无）",
        "- doc_content_gen     生成文档内容（依赖：doc_structure_gen）",
        "- feishu_doc_write    写入飞书文档（依赖：doc_content_gen）",
        "- doc_section_editor  修改文档指定章节（依赖：feishu_doc_write）",
        "- mod_intent_parser   解析修改意图（依赖：无，修改路径专用）",
    ]
    if stage >= 3:
        lines += [
            "- ppt_structure_gen   生成 PPT 大纲（依赖：无）",
            "- ppt_content_gen     生成 PPT 幻灯片内容（依赖：ppt_structure_gen）",
            "- feishu_ppt_write    写入飞书 PPT 并上传云盘（依赖：ppt_content_gen）",
            "- ppt_slide_editor    修改 PPT 指定幻灯片（依赖：feishu_ppt_write）",
        ]
    return "\n".join(lines)
