import pytest

from app.config import Settings, get_settings


def test_config_loads_from_env(mock_env: None) -> None:
    get_settings.cache_clear()
    settings = Settings()
    assert settings.FEISHU_APP_ID == "test_app_id"
    assert settings.FEISHU_APP_SECRET == "test_app_secret"
    assert settings.DOUBAO_MODEL_PRO == "ep-20241230000000-xxxxx"
    assert settings.APP_ENV == "dev"
    assert settings.API_PORT == 8000
    assert settings.CELERY_TASK_TIME_LIMIT == 180


def test_config_defaults(mock_env: None) -> None:
    get_settings.cache_clear()
    settings = Settings()
    assert settings.FEISHU_DOMAIN == "https://open.feishu.cn"
    assert settings.REDIS_URL == "redis://localhost:6379/0"
    assert settings.CHROMA_PORT == 8001
    assert settings.LOG_LEVEL == "INFO"


def test_config_missing_required_field() -> None:
    """Settings without required fields should raise ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
        )


def test_get_settings_singleton(mock_env: None) -> None:
    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()
