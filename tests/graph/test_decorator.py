"""Tests for the @graph_node decorator — race protection and basic plumbing."""

import pytest

from app.graph.nodes._decorator import graph_node


@pytest.mark.asyncio
async def test_race_protection_skips_non_clarify_resume() -> None:
    """Any node with pending_user_action set must return {} (no-op)."""

    @graph_node("intent_parser")
    async def fake_node(state: dict) -> dict:
        return {"intent": "parsed"}

    state = {"pending_user_action": {"kind": "clarify", "request_id": "abc"}}
    result = await fake_node(state)
    assert result == {}


@pytest.mark.asyncio
async def test_clarify_resume_bypasses_race_protection() -> None:
    """clarify_resume must execute even when pending_user_action is set."""

    @graph_node("clarify_resume")
    async def clarify_node(state: dict) -> dict:
        return {"normalized_text": "answered"}

    state = {"pending_user_action": {"kind": "clarify", "request_id": "abc"}}
    result = await clarify_node(state)
    assert result == {"normalized_text": "answered"}


@pytest.mark.asyncio
async def test_normal_node_runs_without_pending_action() -> None:
    """Without pending_user_action, the decorated function executes normally."""

    @graph_node("intent_parser")
    async def normal_node(state: dict) -> dict:
        return {"intent": "parsed"}

    result = await normal_node({"raw_input": "hello"})
    assert result == {"intent": "parsed"}


@pytest.mark.asyncio
async def test_pending_action_none_does_not_block() -> None:
    """pending_user_action=None is treated as absent — node should run."""

    @graph_node("planner")
    async def planner_node(state: dict) -> dict:
        return {"plan": "created"}

    result = await planner_node({"pending_user_action": None, "intent": "x"})
    assert result == {"plan": "created"}


def test_node_name_stored_on_wrapper() -> None:
    @graph_node("my_node")
    async def fn(state: dict) -> dict:
        return {}

    assert fn.__node_name__ == "my_node"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_race_protection_with_empty_dict_pending_action() -> None:
    """An empty dict is falsy — node should run."""

    @graph_node("context_retrieval")
    async def retrieval_node(state: dict) -> dict:
        return {"retrieved": True}

    result = await retrieval_node({"pending_user_action": {}})
    assert result == {"retrieved": True}
