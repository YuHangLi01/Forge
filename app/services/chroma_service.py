"""ChromaDB service with mandatory user_id isolation.

Every query and insert is filtered by user_id.  There is no admin bypass —
if user_id is empty, operations raise ValueError rather than accidentally
exposing another user's data.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _get_chroma_client() -> Any:
    import chromadb

    from app.config import get_settings

    settings = get_settings()
    return chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        tenant=settings.CHROMA_TENANT,
    )


@lru_cache(maxsize=1)
def _get_collection() -> Any:
    from app.config import get_settings

    settings = get_settings()
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


class ChromaService:
    """Business-facing wrapper around a single ChromaDB collection.

    All public methods enforce ``where={"user_id": user_id}`` so that
    cross-user data leakage is structurally impossible.
    """

    def _require_user_id(self, user_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must not be empty — cross-user isolation is mandatory")

    async def add(
        self,
        user_id: str,
        doc_id: str,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._require_user_id(user_id)
        meta: dict[str, Any] = {**(metadata or {}), "user_id": user_id}

        def _add() -> None:
            col = _get_collection()
            col.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[meta],
            )

        await asyncio.to_thread(_add)
        logger.debug("chroma_add", user_id=user_id, doc_id=doc_id)

    async def query(
        self,
        user_id: str,
        query_text: str,
        n_results: int = 5,
        query_embedding: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        self._require_user_id(user_id)

        def _query() -> Any:
            col = _get_collection()
            kwargs: dict[str, Any] = {
                "n_results": n_results,
                "where": {"user_id": user_id},
                "include": ["documents", "metadatas", "distances"],
            }
            if query_embedding is not None:
                kwargs["query_embeddings"] = [query_embedding]
            else:
                kwargs["query_texts"] = [query_text]
            return col.query(**kwargs)

        raw = await asyncio.to_thread(_query)

        results: list[dict[str, Any]] = []
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists, strict=False):
            results.append({"text": doc, "metadata": meta, "distance": dist})

        logger.debug("chroma_query", user_id=user_id, n_results=len(results))
        return results

    async def delete_user_data(self, user_id: str) -> None:
        """Remove all documents belonging to user_id (GDPR / test teardown)."""
        self._require_user_id(user_id)

        def _delete() -> None:
            col = _get_collection()
            col.delete(where={"user_id": user_id})

        await asyncio.to_thread(_delete)
        logger.info("chroma_delete_user", user_id=user_id)
