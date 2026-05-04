"""TokenMeter: fire-and-forget per-node LLM cost tracking."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


async def record_usage(
    *,
    task_id: str,
    node_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Write one cost record to DB. Failures are swallowed — never block the caller."""
    if not task_id:
        return
    try:
        from app.db.engine import get_session
        from app.db.models import CostMetric

        async with get_session() as session:
            record = CostMetric(
                task_id=task_id,
                node_name=node_name,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            session.add(record)
            await session.commit()
        logger.debug(
            "cost_metric_recorded",
            task_id=task_id,
            node=node_name,
            prompt=prompt_tokens,
            completion=completion_tokens,
        )
    except Exception:
        logger.exception("cost_metric_write_failed", task_id=task_id, node=node_name)
