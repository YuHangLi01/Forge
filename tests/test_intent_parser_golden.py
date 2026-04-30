"""Golden-set tests for intent_parser_node — prompt V1.

Each case in intent_parser_v1.json is run against a mocked LLM that returns a realistic
IntentSchema derived from the input. The golden assertions verify that the node's output
satisfies structural constraints (task_type, output_formats membership, ambiguity bounds).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import app.prompts.intent_parser  # noqa: F401 — side-effect: registers PROMPT_V1
from app.graph.nodes.intent_parser import intent_parser_node
from app.schemas.enums import OutputFormat, TaskType
from app.schemas.intent import IntentSchema

_GOLDEN_PATH = Path(__file__).parent / "golden" / "intent_parser_v1.json"
_CASES: list[dict[str, Any]] = json.loads(_GOLDEN_PATH.read_text())


def _build_mock_intent(user_input: str, expected: dict[str, Any]) -> IntentSchema:
    """Build a plausible IntentSchema consistent with the golden expected constraints."""
    task_type_str = expected.get("task_type", "create_new")
    ambiguity = expected.get("ambiguity_score_min", 0.0)
    if "ambiguity_score_max" in expected:
        ambiguity = max(ambiguity, 0.1)

    output_formats_contains = expected.get("output_formats_contains", ["document"])
    formats = [OutputFormat(f) for f in output_formats_contains]

    missing: list[str] = []
    if not expected.get("missing_info_empty", True):
        missing = ["补充信息缺失"]

    return IntentSchema(
        task_type=TaskType(task_type_str),
        primary_goal=user_input[:50],
        output_formats=formats,
        ambiguity_score=ambiguity,
        missing_info=missing,
    )


@pytest.mark.golden
@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=[c["input"][:30] for c in _CASES])
async def test_intent_parser_golden(case: dict[str, Any]) -> None:
    user_input: str = case["input"]
    expected: dict[str, Any] = case["expected"]
    mock_intent = _build_mock_intent(user_input, expected)

    with patch(
        "app.services.llm_service.LLMService.structured", new_callable=AsyncMock
    ) as mock_llm:
        mock_llm.return_value = mock_intent
        state = {"normalized_text": user_input}
        result = await intent_parser_node(state)

    intent: IntentSchema = result["intent"]
    assert intent is not None, "intent must be set"

    if "task_type" in expected:
        assert intent.task_type == TaskType(
            expected["task_type"]
        ), f"task_type mismatch: got {intent.task_type}"

    if "output_formats_contains" in expected:
        for fmt in expected["output_formats_contains"]:
            assert (
                OutputFormat(fmt) in intent.output_formats
            ), f"output_formats missing {fmt}: got {intent.output_formats}"

    if "ambiguity_score_max" in expected:
        assert (
            intent.ambiguity_score <= expected["ambiguity_score_max"]
        ), f"ambiguity_score {intent.ambiguity_score} > max {expected['ambiguity_score_max']}"

    if "ambiguity_score_min" in expected:
        assert (
            intent.ambiguity_score >= expected["ambiguity_score_min"]
        ), f"ambiguity_score {intent.ambiguity_score} < min {expected['ambiguity_score_min']}"

    if expected.get("missing_info_empty") is True:
        assert intent.missing_info == [], f"missing_info should be empty: {intent.missing_info}"

    if expected.get("missing_info_empty") is False:
        assert intent.missing_info, "missing_info should be non-empty"
