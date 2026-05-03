"""Coverage tests for EmbeddingService — mocks sentence_transformers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def _make_model_mock(vector_len: int = 4) -> MagicMock:
    import numpy as np

    model = MagicMock()
    model.encode = MagicMock(
        side_effect=lambda texts, **kw: (
            # Single string → 1-D array so .tolist() → list[float]
            np.array([float(i) for i in range(vector_len)])
            if isinstance(texts, str)
            # Batch of strings → 2-D array so [v.tolist() for v in ...] → list[list[float]]
            else np.array([[float(i) for i in range(vector_len)] for _ in texts])
        )
    )
    return model


class TestEmbeddingService:
    def setup_method(self) -> None:
        # Clear lru_cache so each test gets a fresh mock
        from app.services.embedding_service import _get_model

        _get_model.cache_clear()

    def teardown_method(self) -> None:
        from app.services.embedding_service import _get_model

        _get_model.cache_clear()

    @pytest.mark.asyncio
    async def test_embed_returns_float_list(self) -> None:
        from app.services.embedding_service import EmbeddingService

        model = _make_model_mock()
        with patch("app.services.embedding_service._get_model", return_value=model):
            svc = EmbeddingService()
            result = await svc.embed("hello world")
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_embed_batch_empty_returns_empty(self) -> None:
        from app.services.embedding_service import EmbeddingService

        svc = EmbeddingService()
        result = await svc.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list_of_lists(self) -> None:
        from app.services.embedding_service import EmbeddingService

        model = _make_model_mock()
        with patch("app.services.embedding_service._get_model", return_value=model):
            svc = EmbeddingService()
            result = await svc.embed_batch(["text1", "text2"])
        assert len(result) == 2
        assert all(isinstance(v, list) for v in result)


class TestGetModel:
    def setup_method(self) -> None:
        from app.services.embedding_service import _get_model

        _get_model.cache_clear()

    def teardown_method(self) -> None:
        from app.services.embedding_service import _get_model

        _get_model.cache_clear()

    def test_get_model_loads_sentence_transformer(self, tmp_path) -> None:
        """Lines 23-45: _get_model() with SentenceTransformer mocked."""
        import numpy as np

        mock_st_module = MagicMock()
        mock_model = MagicMock()
        mock_model.encode = MagicMock(return_value=np.array([[0.1, 0.2, 0.3, 0.4]]))
        mock_st_module.SentenceTransformer = MagicMock(return_value=mock_model)

        with (
            patch.dict(sys.modules, {"sentence_transformers": mock_st_module}),
            patch("app.config.get_settings") as mock_settings,
        ):
            settings = MagicMock()
            settings.REDIS_URL = "redis://localhost"
            settings.MODEL_CACHE_DIR = str(tmp_path)
            mock_settings.return_value = settings

            from app.services.embedding_service import _get_model

            _get_model.cache_clear()
            model = _get_model()
            assert model is mock_model
