from datetime import UTC, datetime
from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)


@forge_task(name="forge.echo", queue="fast")  # type: ignore[untyped-decorator]
def echo_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    logger.info("echo_received", payload=payload)
    return {"echo": payload, "ts": datetime.now(UTC).isoformat()}
