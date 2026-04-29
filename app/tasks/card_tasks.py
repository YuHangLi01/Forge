from typing import Any

import structlog

from app.tasks.base import forge_task

logger = structlog.get_logger(__name__)


@forge_task(name="forge.handle_card_action", queue="fast")  # type: ignore[untyped-decorator]
def handle_card_action_task(self: Any, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Handle Feishu interactive card button clicks."""
    logger.info("card_action_received", payload=payload)
    return {"status": "received"}
