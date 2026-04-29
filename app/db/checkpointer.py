import structlog

logger = structlog.get_logger(__name__)


async def create_checkpointer() -> object:
    """Create and setup an AsyncPostgresSaver for LangGraph state persistence.

    LangGraph checkpoint tables are created by setup() — NOT by Alembic.
    The langgraph schema must exist first (created by docker/postgres/init.sql).
    """
    from psycopg_pool import AsyncConnectionPool

    from app.config import get_settings

    settings = get_settings()

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        pool = AsyncConnectionPool(settings.DATABASE_URL, open=False)
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await checkpointer.setup()
        logger.info("checkpointer_ready", schema="langgraph")
        return checkpointer
    except Exception as exc:
        logger.error("checkpointer_setup_failed", error=str(exc))
        raise
