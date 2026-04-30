"""User isolation tests: dev_alice data must never appear in dev_bob's queries."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.chroma_service import ChromaService


@pytest.mark.asyncio
async def test_empty_user_id_raises_on_add() -> None:
    svc = ChromaService()
    with pytest.raises(ValueError, match="user_id must not be empty"):
        await svc.add(user_id="", doc_id="x", text="hello", embedding=[0.1, 0.2])


@pytest.mark.asyncio
async def test_empty_user_id_raises_on_query() -> None:
    svc = ChromaService()
    with pytest.raises(ValueError, match="user_id must not be empty"):
        await svc.query(user_id="", query_text="test")


@pytest.mark.asyncio
async def test_query_always_includes_user_id_where_clause() -> None:
    """Verify where={"user_id": ...} is always passed to Chroma."""
    mock_col = MagicMock()
    mock_col.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    with patch("app.services.chroma_service._get_collection", return_value=mock_col):
        svc = ChromaService()
        await svc.query(user_id="dev_alice", query_text="复盘")

    call_kwargs = mock_col.query.call_args.kwargs
    assert call_kwargs.get("where") == {"user_id": "dev_alice"}


@pytest.mark.asyncio
async def test_alice_data_not_visible_to_bob() -> None:
    """Simulate alice adding data, then bob querying — bob sees nothing."""

    def _fake_query(**kwargs: object) -> dict:
        where = kwargs.get("where", {})
        if isinstance(where, dict) and where.get("user_id") == "dev_alice":
            return {
                "documents": [["alice secret"]],
                "metadatas": [[{"user_id": "dev_alice"}]],
                "distances": [[0.0]],
            }
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    mock_col = MagicMock()
    mock_col.query.side_effect = _fake_query

    with patch("app.services.chroma_service._get_collection", return_value=mock_col):
        svc = ChromaService()
        alice_results = await svc.query(user_id="dev_alice", query_text="secret")
        bob_results = await svc.query(user_id="dev_bob", query_text="secret")

    assert len(alice_results) == 1
    assert alice_results[0]["text"] == "alice secret"
    assert bob_results == []
