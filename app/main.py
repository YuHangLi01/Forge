from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging()

    redis_client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.REDIS_URL, decode_responses=True
    )

    from app.services.event_dedup import set_redis_client

    set_redis_client(redis_client)

    from app.graph import get_or_init_graph

    await get_or_init_graph()

    logger.info("forge_startup", env=settings.APP_ENV)
    yield

    await redis_client.aclose()
    logger.info("forge_shutdown")


app = FastAPI(title="Forge", version="0.1.0", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=str(request.url), error=str(exc), exc_info=exc)
    return JSONResponse(status_code=500, content={"code": -1, "msg": str(exc)})


from app.api.health import router as health_router  # noqa: E402
from app.api.webhook import router as webhook_router  # noqa: E402

app.include_router(health_router)
app.include_router(webhook_router, prefix="/api/v1")


def get_app() -> FastAPI:
    return app
