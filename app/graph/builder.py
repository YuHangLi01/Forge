from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.graph.state import AgentState

# 11 work nodes — all implemented as stubs in T01; wired in T05-T11.
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


async def _stub_node(state: dict[str, Any]) -> dict[str, Any]:
    return {}


def build_graph(checkpointer: Any = None) -> Any:
    """Build and compile the Forge StateGraph.

    All work nodes are stubs in T01.  Routing logic (conditional edges from
    step_router) is wired in T05; individual node implementations follow in
    T06-T11.  The compiled graph is safe to invoke end-to-end; it will run
    preprocess → step_router → END with no side effects.
    """
    graph: StateGraph = StateGraph(AgentState)

    for node_name in ALL_NODES:
        graph.add_node(node_name, _stub_node)

    graph.set_entry_point("preprocess")

    # Minimal skeleton edges — replaced by conditional spider-graph in T05.
    graph.add_edge("preprocess", "step_router")
    graph.add_edge("step_router", END)
    graph.add_edge("error_handler", END)

    return graph.compile(checkpointer=checkpointer)
