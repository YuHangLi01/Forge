import asyncio
import json
from typing import Any, Literal

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.feishu.exceptions import FeishuAPIError, FeishuRateLimitError

logger = structlog.get_logger(__name__)

_RATE_LIMIT_CODE = 99991663


def _check_response(resp: Any, method: str) -> Any:
    """Check lark_oapi response and raise on error."""
    if not resp.success():
        code = getattr(resp, "code", 0)
        msg = getattr(resp, "msg", "unknown error")
        if code == _RATE_LIMIT_CODE:
            raise FeishuRateLimitError(f"{method}: rate limited — {msg}", feishu_code=code)
        raise FeishuAPIError(f"{method}: code={code} msg={msg}", feishu_code=code)
    return resp


class FeishuAdapter:
    """Business-facing Feishu OpenAPI wrapper.

    All methods are async. The lark_oapi SDK is synchronous, so calls are
    dispatched via asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        domain: str | None = None,
    ) -> None:
        import lark_oapi as lark

        from app.config import get_settings

        settings = get_settings()
        _app_id = app_id or settings.FEISHU_APP_ID
        _app_secret = app_secret or settings.FEISHU_APP_SECRET
        _domain = domain or settings.FEISHU_DOMAIN
        self._client = (
            lark.Client.builder().app_id(_app_id).app_secret(_app_secret).domain(_domain).build()
        )
        self._app_id = _app_id

    @retry(
        retry=retry_if_exception_type(FeishuRateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def send_text(self, chat_id: str, text: str) -> str:
        """Send a text message to a chat. Returns message_id."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}))
            .build()
        )
        req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
        resp = await asyncio.to_thread(self._client.im.v1.message.create, req)
        _check_response(resp, "send_text")
        msg_id: str = resp.data.message_id or ""
        logger.info("send_text_ok", chat_id=chat_id, message_id=msg_id)
        return msg_id

    @retry(
        retry=retry_if_exception_type(FeishuRateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def reply_text(self, message_id: str, text: str) -> str:
        """Reply to a specific message. Returns the new message_id."""
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

        body = (
            ReplyMessageRequestBody.builder()
            .content(json.dumps({"text": text}))
            .msg_type("text")
            .build()
        )
        req = ReplyMessageRequest.builder().message_id(message_id).request_body(body).build()
        resp = await asyncio.to_thread(self._client.im.v1.message.reply, req)
        _check_response(resp, "reply_text")
        new_msg_id: str = resp.data.message_id or ""
        logger.info("reply_text_ok", original_message_id=message_id, new_message_id=new_msg_id)
        return new_msg_id

    @retry(
        retry=retry_if_exception_type(FeishuRateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def send_card(self, chat_id: str, card: dict[str, Any]) -> str:
        """Send an interactive card to a chat. Returns message_id."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        body = (
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card))
            .build()
        )
        req = CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build()
        resp = await asyncio.to_thread(self._client.im.v1.message.create, req)
        _check_response(resp, "send_card")
        msg_id: str = resp.data.message_id or ""
        return msg_id

    async def update_card(self, message_id: str, card: dict[str, Any]) -> None:
        """Update an existing card message."""
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

        body = PatchMessageRequestBody.builder().content(json.dumps(card)).build()
        req = PatchMessageRequest.builder().message_id(message_id).request_body(body).build()
        resp = await asyncio.to_thread(self._client.im.v1.message.patch, req)
        _check_response(resp, "update_card")

    async def download_message_resource(
        self, message_id: str, file_key: str, type_: str = "file"
    ) -> bytes:
        """Download a file/audio resource from a message."""
        from lark_oapi.api.im.v1 import GetMessageResourceRequest

        req = (
            GetMessageResourceRequest.builder()
            .message_id(message_id)
            .file_key(file_key)
            .type(type_)
            .build()
        )
        resp = await asyncio.to_thread(self._client.im.v1.message_resource.get, req)
        _check_response(resp, "download_message_resource")
        raw: bytes = resp.file.read()
        return raw

    @retry(
        retry=retry_if_exception_type(FeishuRateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def create_document(self, title: str, folder_token: str | None = None) -> str:
        """Create a new Feishu Doc. Returns doc_token."""
        from lark_oapi.api.docx.v1 import CreateDocumentRequest, CreateDocumentRequestBody

        builder = CreateDocumentRequestBody.builder().title(title)
        if folder_token:
            builder = builder.folder_token(folder_token)
        req = CreateDocumentRequest.builder().request_body(builder.build()).build()
        resp = await asyncio.to_thread(self._client.docx.v1.document.create, req)
        _check_response(resp, "create_document")
        doc_token: str = resp.data.document.document_id or ""
        logger.info("create_document_ok", doc_token=doc_token, title=title)
        return doc_token

    async def batch_update_blocks(
        self, doc_token: str, requests: list[dict[str, Any]]
    ) -> list[str]:
        """Write blocks to a document. Returns list of created block_ids."""
        from lark_oapi.api.docx.v1 import (
            BatchUpdateDocumentBlockRequest,
            BatchUpdateDocumentBlockRequestBody,
        )

        body = BatchUpdateDocumentBlockRequestBody.builder().requests(requests).build()
        req = (
            BatchUpdateDocumentBlockRequest.builder()
            .document_id(doc_token)
            .request_body(body)
            .build()
        )
        resp = await asyncio.to_thread(self._client.docx.v1.document_block.batch_update, req)
        _check_response(resp, "batch_update_blocks")
        block_ids = [r.block_id for r in (resp.data.results or []) if r.block_id]
        return block_ids

    async def get_document_blocks(self, doc_token: str) -> list[dict[str, Any]]:
        """Read all blocks from a document."""
        from lark_oapi.api.docx.v1 import ListDocumentBlockRequest

        req = ListDocumentBlockRequest.builder().document_id(doc_token).build()
        resp = await asyncio.to_thread(self._client.docx.v1.document_block.list, req)
        _check_response(resp, "get_document_blocks")
        blocks: list[dict[str, Any]] = []
        for item in resp.data.items or []:
            blocks.append({"block_id": item.block_id, "block_type": item.block_type})
        return blocks

    async def get_share_url(
        self, token: str, type_: Literal["doc", "slide", "file"] = "doc"
    ) -> str:
        """Get a sharable URL for a document/file."""
        domain = "https://open.feishu.cn"
        type_map = {"doc": "docx", "slide": "slides", "file": "file"}
        path_type = type_map.get(type_, "docx")
        return f"{domain}/{path_type}/{token}"

    @classmethod
    def from_settings(cls) -> "FeishuAdapter":
        from app.config import get_settings

        settings = get_settings()
        return cls(
            app_id=settings.FEISHU_APP_ID,
            app_secret=settings.FEISHU_APP_SECRET,
            domain=settings.FEISHU_DOMAIN,
        )
