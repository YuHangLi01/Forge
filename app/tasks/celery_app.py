from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "forge",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.tasks.message_tasks.*": {"queue": "slow"},
        "app.tasks.demo_tasks.*": {"queue": "slow"},
        "app.tasks.card_tasks.*": {"queue": "fast"},
        "app.tasks.echo_tasks.*": {"queue": "fast"},
    },
    imports=(
        "app.tasks.message_tasks",
        "app.tasks.demo_tasks",
        "app.tasks.card_tasks",
        "app.tasks.echo_tasks",
    ),
)
