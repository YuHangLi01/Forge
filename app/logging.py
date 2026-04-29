import logging
import sys
from collections.abc import Generator
from contextlib import contextmanager

import structlog

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    is_production = settings.APP_ENV == "prod"

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    # Route uvicorn and sqlalchemy logs through structlog
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(logger_name).handlers.clear()
        logging.getLogger(logger_name).propagate = True


@contextmanager
def bind_task_context(
    task_id: str,
    user_id: str = "",
    chat_id: str = "",
) -> Generator[None, None, None]:
    structlog.contextvars.bind_contextvars(
        task_id=task_id,
        user_id=user_id,
        chat_id=chat_id,
    )
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars("task_id", "user_id", "chat_id")
