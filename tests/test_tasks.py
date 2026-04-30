"""Tests for Celery task infrastructure using task_always_eager mode."""

import pytest


@pytest.fixture(autouse=True)
def celery_eager(mock_env: None) -> None:
    """Run Celery tasks synchronously in tests (requires mock_env for Settings)."""
    from app.config import get_settings

    get_settings.cache_clear()
    from app.tasks.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    get_settings.cache_clear()


def test_echo_task_returns_payload() -> None:
    from app.tasks.echo_tasks import echo_task

    result = echo_task.apply(args=[{"hello": "world"}]).get()
    assert result["echo"] == {"hello": "world"}
    assert "ts" in result


def test_card_action_task_returns_received() -> None:
    from app.tasks.card_tasks import handle_card_action_task

    result = handle_card_action_task.apply(args=[{"action": "test"}]).get()
    # Unknown action_kind → "unhandled" (stub replaced by real routing in T08)
    assert result["status"] == "unhandled"


def test_message_task_returns_received() -> None:
    from app.tasks.message_tasks import handle_message_task

    payload = {
        "schema": "2.0",
        "header": {"event_id": "ev_001", "event_type": "im.message.receive_v1"},
        "event": {"message": {"message_type": "text", "chat_id": "c1"}},
    }
    result = handle_message_task.apply(args=[payload]).get()
    assert result["status"] == "received"


def test_celery_app_has_correct_queues() -> None:
    from app.tasks.celery_app import celery_app

    routes = celery_app.conf.task_routes
    assert "app.tasks.message_tasks.*" in routes
    assert routes["app.tasks.message_tasks.*"]["queue"] == "slow"
    assert routes["app.tasks.card_tasks.*"]["queue"] == "fast"
