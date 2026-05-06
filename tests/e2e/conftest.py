"""E2E test configuration.

Provides environment patching for e2e tests that run the full compiled graph.
The settings cache is cleared before each test so FORGE_STAGE takes effect.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required Settings fields and clear the lru_cache for get_settings."""
    from app.config import get_settings

    get_settings.cache_clear()

    env = {
        "FEISHU_APP_ID": "test_app_id",
        "FEISHU_APP_SECRET": "test_app_secret",
        "FEISHU_VERIFICATION_TOKEN": "test_token",
        "FEISHU_ENCRYPT_KEY": "test_encrypt_key_32byteslong12345",
        "DOUBAO_API_KEY": "test_doubao_key",
        "DOUBAO_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        "DOUBAO_MODEL_PRO": "ep-20241230000000-xxxxx",
        "DOUBAO_MODEL_LITE": "ep-20241230000000-yyyyy",
        "VOLC_ASR_APP_ID": "test_asr_app_id",
        "VOLC_ASR_ACCESS_TOKEN": "test_asr_token",
        "DATABASE_URL": "postgresql+psycopg://forge:forge@localhost:5432/forge",
        "DATABASE_URL_SYNC": "postgresql+psycopg://forge:forge@localhost:5432/forge",
        "FORGE_USE_GRAPH": "true",
        "FORGE_STAGE": "3",  # Allow all pipeline nodes
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    yield

    # Clear cache after test so next test gets fresh settings
    get_settings.cache_clear()
