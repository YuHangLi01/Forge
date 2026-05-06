"""Feishu OAuth 2.0 callback router.

GET /api/v1/oauth/feishu/callback?code=<code>&state=<state>

Flow:
  1. Exchange code for tokens via Feishu authen API
  2. Store tokens in DB (per user_id = state)
  3. Notify user via Feishu IM that authorization succeeded
  4. Return a self-closing HTML page
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["oauth"])


@router.get("/oauth/feishu/callback", response_class=HTMLResponse)
async def feishu_oauth_callback(
    code: str = Query(..., description="飞书授权码"),
    state: str = Query(..., description="state，即 user_id (open_id)"),
) -> HTMLResponse:
    """Handle Feishu OAuth 2.0 redirect after user approves calendar access."""
    from app.db.engine import get_session
    from app.integrations.feishu.oauth import exchange_code, store_token

    user_id = state

    try:
        token_data = await exchange_code(code, state)
    except Exception as exc:
        logger.error("feishu_oauth_exchange_failed", user_id=user_id, error=str(exc))
        return HTMLResponse(
            content=_page(success=False, message="授权失败，请稍后重试"),
            status_code=400,
        )

    try:
        async with get_session() as db:
            await store_token(user_id, token_data, db)
    except Exception as exc:
        logger.error("feishu_oauth_store_failed", user_id=user_id, error=str(exc))
        return HTMLResponse(
            content=_page(success=False, message="Token 存储失败，请联系管理员"),
            status_code=500,
        )

    try:
        await _notify_user(user_id)
    except Exception:
        logger.warning("feishu_oauth_notify_failed", user_id=user_id, exc_info=True)

    try:
        await _resume_paused_graph(user_id)
    except Exception:
        logger.warning("feishu_oauth_resume_failed", user_id=user_id, exc_info=True)

    logger.info("feishu_oauth_callback_success", user_id=user_id)
    return HTMLResponse(
        content=_page(success=True, message="授权成功！您现在可以关闭此页面。"),
        status_code=200,
    )


async def _resume_paused_graph(user_id: str) -> None:
    """If a graph was paused awaiting this user's calendar auth, resume it.

    Pop the (thread_id, chat_id) mapping from Redis, clear the pending gate
    plus the placeholder intent, then dispatch resume_graph_task. step_router
    will route back to intent_parser, which now finds a valid token.
    """
    from app.graph import get_or_init_graph
    from app.services.oauth_pause import pop_oauth_pending
    from app.tasks.message_tasks import resume_graph_task

    pending = await pop_oauth_pending(user_id)
    if not pending:
        return

    thread_id = pending.get("thread_id", "")
    chat_id = pending.get("chat_id", "")
    if not thread_id:
        return

    graph = await get_or_init_graph()
    config = {"configurable": {"thread_id": thread_id}}
    await graph.aupdate_state(
        config,
        {"pending_user_action": None, "intent": None},
        as_node="step_router",
    )
    resume_graph_task.delay(thread_id, chat_id)
    logger.info("feishu_oauth_paused_graph_resumed", user_id=user_id, thread_id=thread_id)


async def _notify_user(user_id: str) -> None:
    """Send a Feishu DM to user_id confirming calendar authorization."""
    from app.integrations.feishu.adapter import FeishuAdapter

    await FeishuAdapter().send_text(
        user_id,
        "日历授权成功！Forge 现在可以查看您的日程，" "为您提供更精准的日程相关助手服务。",
    )


def _page(success: bool, message: str) -> str:
    icon = "✅" if success else "❌"
    color = "#4CAF50" if success else "#f44336"
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Forge 日历授权</title>
  <style>
    body{{font-family:-apple-system,sans-serif;display:flex;align-items:center;
         justify-content:center;height:100vh;margin:0;background:#f5f5f5;}}
    .card{{background:white;border-radius:12px;padding:40px;text-align:center;
           box-shadow:0 4px 20px rgba(0,0,0,.1);max-width:400px;}}
    .icon{{font-size:56px;}}
    h2{{color:{color};margin:16px 0 8px;}}
    p{{color:#666;}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h2>{message}</h2>
    <p>您可以关闭此页面，返回飞书继续使用。</p>
  </div>
</body>
</html>"""
