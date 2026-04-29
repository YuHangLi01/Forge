from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_engine = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> object:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=10,
            max_overflow=5,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        from sqlalchemy.ext.asyncio import AsyncEngine

        engine = get_engine()
        assert isinstance(engine, AsyncEngine)
        _async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
