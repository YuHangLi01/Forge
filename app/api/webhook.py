import json

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.services.event_dedup import is_duplicate
from app.services.feishu_security import decrypt_message, is_url_verification, verify_signature

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["webhook"])


@router.post("/webhook/feishu")
async def feishu_webhook(request: Request) -> JSONResponse:
    body = await request.body()

    # Parse raw payload (may be encrypted)
    try:
        payload: dict[str, object] = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="invalid JSON body") from exc

    # Step 1: Decrypt if encrypted
    if "encrypt" in payload:
        from app.config import get_settings

        settings = get_settings()
        payload = decrypt_message(str(payload["encrypt"]), settings.FEISHU_ENCRYPT_KEY)

    # Step 2: URL verification (must happen before signature check)
    if challenge := is_url_verification(payload):
        return JSONResponse({"challenge": challenge})

    # Step 3: Signature verification (V2 HMAC-SHA256)
    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")

    if signature:
        from app.config import get_settings

        settings = get_settings()
        if not verify_signature(timestamp, nonce, body, signature, settings.FEISHU_ENCRYPT_KEY):
            raise HTTPException(status_code=401, detail="invalid signature")

    # Step 4: Event deduplication
    header = payload.get("header", {})
    event_id = str(header.get("event_id", "")) if isinstance(header, dict) else ""

    if event_id and await is_duplicate(event_id):
        logger.debug("event_duplicate_skipped", event_id=event_id)
        return JSONResponse({"code": 0})

    # Step 5: Route to Celery task
    event_type = str(header.get("event_type", "")) if isinstance(header, dict) else ""

    if event_type == "im.message.receive_v1":
        from app.tasks.message_tasks import handle_message_task

        handle_message_task.delay(payload)
        logger.info("message_task_dispatched", event_id=event_id)
    elif event_type == "card.action.trigger":
        from app.tasks.card_tasks import handle_card_action_task

        handle_card_action_task.delay(payload)
        logger.info("card_task_dispatched", event_id=event_id)
    else:
        logger.warning("unhandled_event_type", event_type=event_type, event_id=event_id)

    return JSONResponse({"code": 0})
