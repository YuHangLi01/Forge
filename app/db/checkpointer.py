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

        # AsyncConnectionPool needs a libpq-style URL (no SQLAlchemy driver prefix).
        # autocommit=True + prepare_threshold=0 are required by LangGraph's setup():
        # CREATE INDEX CONCURRENTLY cannot run inside a transaction block, and
        # prepared statements are incompatible with LangGraph's explicit transactions.
        db_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        pool = AsyncConnectionPool(
            db_url,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await checkpointer.setup()
        logger.info("checkpointer_ready", schema="langgraph")
        return checkpointer
    except Exception as exc:
        logger.error("checkpointer_setup_failed", error=str(exc))
        raise
