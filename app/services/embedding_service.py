"""Embedding service wrapping bge-m3 via sentence-transformers.

Model is loaded once per process into a module-level singleton so that
Linux Celery prefork workers share the same loaded weights (copy-on-write
semantics after fork).  Cold start is 1-2 GB; subsequent calls are fast.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_MODEL_NAME = "BAAI/bge-m3"


@lru_cache(maxsize=1)
def _get_model() -> Any:
    """Load bge-m3 once; cached for the lifetime of the process."""
    from sentence_transformers import SentenceTransformer

    from app.config import get_settings

    settings = get_settings()
    default_cache = Path.home() / ".cache" / "forge" / "models" / "bge-m3"
    cache_dir = Path(getattr(settings, "MODEL_CACHE_DIR", default_cache))
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info("embedding_model_loading", model=_MODEL_NAME, cache_dir=str(cache_dir))
    model = SentenceTransformer(_MODEL_NAME, cache_folder=str(cache_dir))
    logger.info("embedding_model_ready", model=_MODEL_NAME)
    return model


class EmbeddingService:
    """Thin async wrapper around bge-m3 / sentence-transformers."""

    async def embed(self, text: str) -> list[float]:
        """Return a float32 embedding for *text*."""
        model = _get_model()
        result: list[float] = await asyncio.to_thread(
            lambda: model.encode(text, normalize_embeddings=True).tolist()
        )
        return result

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for all *texts* in a single model call."""
        if not texts:
            return []
        model = _get_model()
        results: list[list[float]] = await asyncio.to_thread(
            lambda: [
                v.tolist()
                for v in model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            ]
        )
        return results
