from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.graph.state import AgentState

# Work nodes — Stage 2: doc pipeline; Stage 3: +ppt pipeline.
WORK_NODES: list[str] = [
    "preprocess",
    "intent_parser",
    "clarify_question",
    "clarify_resume",
    "context_retrieval",
    "planner",
    # doc pipeline (Stage 2)
    "doc_structure_gen",
    "doc_content_gen",
    "feishu_doc_write",
    "mod_intent_parser",
    "doc_section_editor",
    # ppt pipeline (Stage 3)
    "ppt_structure_gen",
    "ppt_content_gen",
    "feishu_ppt_write",
    "ppt_slide_editor",
]

# Routing/terminal nodes
ROUTING_NODES: list[str] = ["step_router", "error_handler"]

ALL_NODES: list[str] = WORK_NODES + ROUTING_NODES

# All nodes that feed into step_router (the spider graph "legs")
_ROUTED_WORK_NODES: list[str] = [
    "preprocess",
    "intent_parser",
    "clarify_resume",
    "context_retrieval",
    "planner",
    # doc pipeline
    "doc_structure_gen",
    "doc_content_gen",
    "feishu_doc_write",
    "mod_intent_parser",
    "doc_section_editor",
    # ppt pipeline
    "ppt_structure_gen",
    "ppt_content_gen",
    "feishu_ppt_write",
    "ppt_slide_editor",
]

# step_router can route to any of these destinations
_ROUTER_TARGETS: dict[str, str] = {
    node: node
    for node in [
        "intent_parser",
        "clarify_question",
        "clarify_resume",
        "context_retrieval",
        "planner",
        # doc pipeline
        "doc_structure_gen",
        "doc_content_gen",
        "feishu_doc_write",
        "mod_intent_parser",
        "doc_section_editor",
        # ppt pipeline
        "ppt_structure_gen",
        "ppt_content_gen",
        "feishu_ppt_write",
        "ppt_slide_editor",
        "error_handler",
    ]
}
_ROUTER_TARGETS[END] = END


def build_graph(checkpointer: Any = None) -> Any:
    """Build and compile the Forge StateGraph.

    Spider-graph topology: every work node feeds into step_router, which
    conditionally routes to the next work node (or END / error_handler).
    step_router routing logic is in app.graph.nodes.step_router.route().
    """
    from app.graph.nodes.clarify_question import clarify_question_node
    from app.graph.nodes.clarify_resume import clarify_resume_node
    from app.graph.nodes.context_retrieval import context_retrieval_node
    from app.graph.nodes.doc_content_gen import doc_content_gen_node
    from app.graph.nodes.doc_section_editor import doc_section_editor_node
    from app.graph.nodes.doc_structure_gen import doc_structure_gen_node
    from app.graph.nodes.error_handler import error_handler_node
    from app.graph.nodes.feishu_doc_write import feishu_doc_write_node
    from app.graph.nodes.feishu_ppt_write import feishu_ppt_write_node
    from app.graph.nodes.intent_parser import intent_parser_node
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node
    from app.graph.nodes.planner import planner_node
    from app.graph.nodes.ppt_content_gen import ppt_content_gen_node
    from app.graph.nodes.ppt_slide_editor import ppt_slide_editor_node
    from app.graph.nodes.ppt_structure_gen import ppt_structure_gen_node
    from app.graph.nodes.preprocess import preprocess_node
    from app.graph.nodes.step_router import route, step_router_node

    work_node_impls: dict[str, Any] = {
        "preprocess": preprocess_node,
        "intent_parser": intent_parser_node,
        "clarify_question": clarify_question_node,
        "clarify_resume": clarify_resume_node,
        "context_retrieval": context_retrieval_node,
        "planner": planner_node,
        "doc_structure_gen": doc_structure_gen_node,
        "doc_content_gen": doc_content_gen_node,
        "feishu_doc_write": feishu_doc_write_node,
        "mod_intent_parser": mod_intent_parser_node,
        "doc_section_editor": doc_section_editor_node,
        "ppt_structure_gen": ppt_structure_gen_node,
        "ppt_content_gen": ppt_content_gen_node,
        "feishu_ppt_write": feishu_ppt_write_node,
        "ppt_slide_editor": ppt_slide_editor_node,
    }

    graph: StateGraph[AgentState, AgentState, Any] = StateGraph(AgentState)

    for node_name in WORK_NODES:
        graph.add_node(node_name, work_node_impls[node_name])
    graph.add_node("step_router", step_router_node)  # type: ignore[type-var]
    graph.add_node("error_handler", error_handler_node)

    # Entry point
    graph.set_entry_point("preprocess")

    # Spider legs: all routed work nodes → step_router
    for node_name in _ROUTED_WORK_NODES:
        graph.add_edge(node_name, "step_router")

    # clarify_question sets pending_user_action and pauses; it also goes to step_router
    # so the graph can save state before halting at END
    graph.add_edge("clarify_question", "step_router")

    # step_router dispatches conditionally to every possible next node
    graph.add_conditional_edges("step_router", route, _ROUTER_TARGETS)  # type: ignore[arg-type]

    # error_handler is a terminal node
    graph.add_edge("error_handler", END)

    return graph.compile(checkpointer=checkpointer)
