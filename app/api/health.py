import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.event_dedup import get_redis_client

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness() -> JSONResponse:
    """Check that Redis is reachable. PostgreSQL check is optional for Stage 1."""
    try:
        client = get_redis_client()
        await client.ping()
    except Exception as exc:
        logger.warning("readiness_check_failed", error=str(exc))
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(exc)})
    return JSONResponse(status_code=200, content={"status": "ok"})
