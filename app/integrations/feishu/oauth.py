"""Feishu OAuth 2.0 per-user token management for calendar access.

Public API:
  get_auth_url(user_id) -> str
  exchange_code(code, state) -> dict
  store_token(user_id, token_data, db) -> None
  get_valid_token(user_id, db) -> str | None
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_REFRESH_BUFFER_SECONDS = 300  # refresh 5 min before expiry to avoid edge-case races


def get_auth_url(user_id: str) -> str:
    """Build the Feishu OAuth 2.0 authorization URL for this user.

    state encodes the user_id (open_id) so the callback knows who to store tokens for.
    """
    from app.config import get_settings

    settings = get_settings()
    redirect_uri = f"{settings.FORGE_PUBLIC_URL.rstrip('/')}/api/v1/oauth/feishu/callback"
    params = {
        "app_id": settings.FEISHU_APP_ID,
        "redirect_uri": redirect_uri,
        "scope": "calendar:calendar:readonly",
        "state": user_id,
    }
    return "https://open.feishu.cn/open-apis/authen/v1/authorize?" + urlencode(params)


async def exchange_code(code: str, state: str) -> dict[str, Any]:  # noqa: ARG001
    """Exchange an authorization code for access_token + refresh_token.

    Uses lark_oapi authen.v1.access_token.acreate (native async, no to_thread needed).
    Returns a dict ready for store_token().
    """
    import lark_oapi as lark
    from lark_oapi.api.authen.v1 import (
        CreateAccessTokenRequest,
        CreateAccessTokenRequestBody,
    )

    from app.config import get_settings

    settings = get_settings()
    client = (
        lark.Client.builder()
        .app_id(settings.FEISHU_APP_ID)
        .app_secret(settings.FEISHU_APP_SECRET)
        .build()
    )

    body = (
        CreateAccessTokenRequestBody.builder().grant_type("authorization_code").code(code).build()
    )
    req = CreateAccessTokenRequest.builder().request_body(body).build()
    resp = await client.authen.v1.access_token.acreate(req)

    if not resp.success():
        raise RuntimeError(f"exchange_code failed: code={resp.code} msg={resp.msg}")

    data = resp.data
    now = datetime.now(UTC)
    return {
        "access_token": data.access_token,
        "refresh_token": data.refresh_token,
        "expires_at": now + timedelta(seconds=data.expires_in or 7200),
        "refresh_expires_at": now + timedelta(seconds=data.refresh_expires_in or 2592000),
        "scope": "calendar:calendar:readonly",
        "open_id": data.open_id,
    }


async def store_token(user_id: str, token_data: dict[str, Any], db: AsyncSession) -> None:
    """Upsert token_data into feishu_oauth_tokens for user_id."""
    from app.db.models import FeishuOAuthToken

    result = await db.execute(select(FeishuOAuthToken).where(FeishuOAuthToken.user_id == user_id))
    row = result.scalar_one_or_none()
    now = datetime.now(UTC)

    if row is None:
        row = FeishuOAuthToken(
            user_id=user_id,
            access_token=token_data["access_token"],
            refresh_token=token_data["refresh_token"],
            expires_at=token_data["expires_at"],
            refresh_expires_at=token_data["refresh_expires_at"],
            scope=token_data.get("scope", ""),
            open_id=token_data.get("open_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.access_token = token_data["access_token"]
        row.refresh_token = token_data["refresh_token"]
        row.expires_at = token_data["expires_at"]
        row.refresh_expires_at = token_data["refresh_expires_at"]
        row.scope = token_data.get("scope", row.scope)
        if token_data.get("open_id"):
            row.open_id = token_data["open_id"]
        row.updated_at = now

    await db.commit()
    logger.info("feishu_oauth_token_stored", user_id=user_id)


async def get_valid_token(user_id: str, db: AsyncSession) -> str | None:
    """Return a valid access_token for user_id, refreshing if needed.

    Returns None when the user has not authorized or refresh_token has expired
    (caller should trigger re-authorization).
    """
    from app.db.models import FeishuOAuthToken

    result = await db.execute(select(FeishuOAuthToken).where(FeishuOAuthToken.user_id == user_id))
    row = result.scalar_one_or_none()

    if row is None:
        logger.debug("feishu_oauth_token_not_found", user_id=user_id)
        return None

    now = datetime.now(UTC)

    # refresh_token itself has expired → must re-authorize from scratch
    if now >= row.refresh_expires_at:
        logger.info(
            "feishu_oauth_refresh_token_expired",
            user_id=user_id,
            expired_at=row.refresh_expires_at.isoformat(),
        )
        await db.delete(row)
        await db.commit()
        return None

    # access_token still valid (with buffer)
    if now < row.expires_at - timedelta(seconds=_REFRESH_BUFFER_SECONDS):
        return row.access_token

    # access_token about to expire — refresh silently
    logger.info("feishu_oauth_token_refreshing", user_id=user_id)
    try:
        new_data = await _refresh_token(user_id, row.refresh_token)
        await store_token(user_id, new_data, db)
        logger.info("feishu_oauth_token_refreshed", user_id=user_id)
        return str(new_data["access_token"])
    except Exception as exc:
        logger.warning("feishu_oauth_token_refresh_failed", user_id=user_id, error=str(exc))
        # Fall back to the existing token if it hasn't technically expired yet
        if now < row.expires_at:
            return row.access_token
        return None


async def _refresh_token(user_id: str, refresh_token_val: str) -> dict[str, Any]:
    import lark_oapi as lark
    from lark_oapi.api.authen.v1 import (
        CreateRefreshAccessTokenRequest,
        CreateRefreshAccessTokenRequestBody,
    )

    from app.config import get_settings

    settings = get_settings()
    client = (
        lark.Client.builder()
        .app_id(settings.FEISHU_APP_ID)
        .app_secret(settings.FEISHU_APP_SECRET)
        .build()
    )

    body = (
        CreateRefreshAccessTokenRequestBody.builder()
        .grant_type("refresh_token")
        .refresh_token(refresh_token_val)
        .build()
    )
    req = CreateRefreshAccessTokenRequest.builder().request_body(body).build()
    resp = await client.authen.v1.refresh_access_token.acreate(req)

    if not resp.success():
        raise RuntimeError(
            f"refresh_token failed for user={user_id}: code={resp.code} msg={resp.msg}"
        )

    data = resp.data
    now = datetime.now(UTC)
    return {
        "access_token": data.access_token,
        "refresh_token": data.refresh_token,
        "expires_at": now + timedelta(seconds=data.expires_in or 7200),
        "refresh_expires_at": now + timedelta(seconds=data.refresh_expires_in or 2592000),
        "scope": "calendar:calendar:readonly",
        "open_id": data.open_id,
    }
