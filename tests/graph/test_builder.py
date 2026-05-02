"""Tests for build_graph — verifies the StateGraph compiles and all nodes are registered."""

from app.graph.builder import ALL_NODES, WORK_NODES, build_graph


def test_build_graph_compiles_with_none_checkpointer() -> None:
    compiled = build_graph(None)
    assert compiled is not None


def test_build_graph_compiles_without_argument() -> None:
    compiled = build_graph()
    assert compiled is not None


def test_all_work_nodes_in_all_nodes_list() -> None:
    for node in WORK_NODES:
        assert node in ALL_NODES


def test_all_nodes_count() -> None:
    assert len(WORK_NODES) == 17  # 11 doc-pipeline + 4 ppt-pipeline + 2 lego orchestration
    assert len(ALL_NODES) == 20  # 17 work + step_router + error_handler + checkpoint_control


def test_build_graph_returns_different_instances() -> None:
    g1 = build_graph(None)
    g2 = build_graph(None)
    assert g1 is not g2


def test_every_work_node_has_real_coroutine_implementation() -> None:
    """Regression guard: a previous build_graph wired every work node to
    `_stub_node` (returns {}), causing step_router to loop and trip
    GraphRecursionError on first message. Verify each WORK_NODES entry
    has a real `<name>_node` coroutine in app.graph.nodes.<name>.
    """
    import importlib
    import inspect

    for node_name in WORK_NODES:
        module = importlib.import_module(f"app.graph.nodes.{node_name}")
        fn = getattr(module, f"{node_name}_node", None)
        assert fn is not None, f"missing {node_name}_node in app.graph.nodes.{node_name}"
        unwrapped = fn
        while hasattr(unwrapped, "__wrapped__"):
            unwrapped = unwrapped.__wrapped__
        assert inspect.iscoroutinefunction(
            unwrapped
        ), f"{node_name}_node is not a coroutine: {fn!r}"


def test_get_graph_singleton_returns_same_instance() -> None:
    from app.graph import get_graph, reset_graph

    reset_graph()
    g1 = get_graph()
    g2 = get_graph()
    assert g1 is g2
    reset_graph()


def test_reset_graph_clears_singleton() -> None:
    from app.graph import get_graph, reset_graph

    reset_graph()
    g1 = get_graph()
    reset_graph()
    g2 = get_graph()
    assert g1 is not g2
    reset_graph()
