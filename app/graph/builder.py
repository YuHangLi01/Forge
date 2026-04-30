from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.graph.state import AgentState

# 11 work nodes — stubs in T01; individual implementations land in T06-T11.
WORK_NODES: list[str] = [
    "preprocess",
    "intent_parser",
    "clarify_question",
    "clarify_resume",
    "context_retrieval",
    "planner",
    "doc_structure_gen",
    "doc_content_gen",
    "feishu_doc_write",
    "mod_intent_parser",
    "doc_section_editor",
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
    "doc_structure_gen",
    "doc_content_gen",
    "feishu_doc_write",
    "mod_intent_parser",
    "doc_section_editor",
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
        "doc_structure_gen",
        "doc_content_gen",
        "feishu_doc_write",
        "mod_intent_parser",
        "doc_section_editor",
        "error_handler",
    ]
}
_ROUTER_TARGETS[END] = END


async def _stub_node(state: dict[str, Any]) -> dict[str, Any]:
    return {}


def build_graph(checkpointer: Any = None) -> Any:
    """Build and compile the Forge StateGraph.

    Spider-graph topology: every work node feeds into step_router, which
    conditionally routes to the next work node (or END / error_handler).
    Individual node implementations land in T06-T11; step_router routing
    logic is in app.graph.nodes.step_router.route().
    """
    from app.graph.nodes.step_router import route, step_router_node

    graph: StateGraph[AgentState, AgentState, Any] = StateGraph(AgentState)

    # Register all nodes — work nodes as stubs, step_router with real logic
    for node_name in WORK_NODES:
        graph.add_node(node_name, _stub_node)  # type: ignore[type-var]
    graph.add_node("step_router", step_router_node)  # type: ignore[type-var]
    graph.add_node("error_handler", _stub_node)  # type: ignore[type-var]

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
