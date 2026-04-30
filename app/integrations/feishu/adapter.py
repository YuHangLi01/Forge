import asyncio
import json
from typing import Any, Literal

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.feishu.exceptions import FeishuAPIError, FeishuRateLimitError

logger = structlog.get_logger(__name__)

_RATE_LIMIT_CODE = 99991663
# Max children per single create_document_block_children call. Feishu's docx
# v1 returns 99992402 'field validation failed' once the array gets too
# large (observed: 85 children fails; 30 is comfortably under the limit).
_MAX_CHILDREN_PER_CALL = 30


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
        self,
        doc_token: str,
        children: list[dict[str, Any]],
        parent_block_id: str | None = None,
    ) -> list[str]:
        """Append a list of blocks under the given parent in a document.

        Uses POST /open-apis/docx/v1/documents/{document_id}/blocks/{parent_block_id}/children
        which expects a flat list of block payloads. By default ``parent_block_id``
        is the document_id (root); pass a specific block_id to nest.

        Feishu's docx v1 API rejects single requests carrying too many
        children (observed: 85 children fails with code 99992402 'field
        validation failed' even when individual blocks are schema-valid).
        We split the work into chunks of at most ``_MAX_CHILDREN_PER_CALL``
        and POST them in order, accumulating the returned block_ids.
        """
        if not children:
            return []
        parent = parent_block_id or doc_token
        all_block_ids: list[str] = []
        for i in range(0, len(children), _MAX_CHILDREN_PER_CALL):
            chunk = children[i : i + _MAX_CHILDREN_PER_CALL]
            chunk_ids = await self._create_block_children(doc_token, parent, chunk)
            all_block_ids.extend(chunk_ids)
        return all_block_ids

    async def _create_block_children(
        self,
        doc_token: str,
        parent_block_id: str,
        children: list[dict[str, Any]],
    ) -> list[str]:
        """One ``create_document_block_children`` call. Logs raw payload on failure."""
        from lark_oapi.api.docx.v1 import (
            CreateDocumentBlockChildrenRequest,
            CreateDocumentBlockChildrenRequestBody,
        )

        body = CreateDocumentBlockChildrenRequestBody.builder().children(children).index(-1).build()
        req = (
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(doc_token)
            .block_id(parent_block_id)
            .request_body(body)
            .build()
        )
        resp = await asyncio.to_thread(self._client.docx.v1.document_block_children.create, req)
        if not resp.success():
            first = children[0] if children else None
            logger.warning(
                "batch_update_blocks_failed",
                doc_token=doc_token,
                code=getattr(resp, "code", 0),
                msg=getattr(resp, "msg", ""),
                child_count=len(children),
                first_block=json.dumps(first, ensure_ascii=False) if first is not None else None,
            )
        _check_response(resp, "batch_update_blocks")
        return [c.block_id for c in (resp.data.children or []) if c.block_id]

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

    @retry(
        retry=retry_if_exception_type(FeishuRateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def upload_drive_file(
        self,
        name: str,
        content: bytes,
        parent_token: str = "",
        parent_type: str = "explorer",
    ) -> str:
        """Upload a binary file to Feishu Drive. Returns the new file_token.

        ``parent_token`` empty → upload to the user's own root explorer;
        non-empty → folder_token returned by ``create_folder`` or pasted
        from a Feishu URL.
        """
        from io import BytesIO

        from lark_oapi.api.drive.v1 import UploadAllFileRequest, UploadAllFileRequestBody

        body = (
            UploadAllFileRequestBody.builder()
            .file_name(name)
            .parent_type(parent_type)
            .parent_node(parent_token)
            .size(len(content))
            .file(BytesIO(content))
            .build()
        )
        req = UploadAllFileRequest.builder().request_body(body).build()
        resp = await asyncio.to_thread(self._client.drive.v1.file.upload_all, req)
        _check_response(resp, "upload_drive_file")
        file_token: str = resp.data.file_token or ""
        logger.info(
            "upload_drive_file_ok",
            file_token=file_token,
            name=name,
            bytes_len=len(content),
        )
        return file_token

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
