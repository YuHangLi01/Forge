import pytest


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch all required Settings fields with dummy values for unit tests."""
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
        # Ensure tests always use Stage 1 path regardless of server .env
        "FORGE_USE_GRAPH": "false",
        "FORGE_STAGE": "2",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
