"""PPT service — Stage 1 path: outline → python-pptx → bytes (→ optional Drive upload).

Per `docs/risk-reports/ppt_strategy_decision.md`, Stage 1 ships option B:
build the deck with python-pptx and surface bytes. Uploading to Feishu
Drive (so the user can preview / share inside Feishu) is wired but skipped
when no FeishuAdapter is provided — useful for local generation and tests.
"""

import asyncio

import structlog

from app.integrations.python_pptx.builder import PptxBuilder
from app.schemas.artifacts import PPTArtifact, SlideSchema

logger = structlog.get_logger(__name__)


class PPTService:
    """Build PowerPoint decks from a structured outline.

    The default builder is python-pptx; pass a different `builder` only for
    tests. `adapter` is optional — when provided, `create_from_outline` will
    upload the resulting bytes to Feishu Drive and populate `PPTArtifact.ppt_id`
    / `share_url`. When omitted (Stage 1 default), the artifact carries an
    empty ppt_id and the caller is expected to consume the bytes directly
    (e.g. write to disk or hand off to another upload path).
    """

    def __init__(
        self,
        builder: PptxBuilder | None = None,
        adapter: object | None = None,
    ) -> None:
        self._builder = builder or PptxBuilder()
        self._adapter = adapter

    async def create_from_outline(
        self,
        title: str,
        slides: list[SlideSchema],
        subtitle: str = "",
    ) -> PPTArtifact:
        """Render the outline into a .pptx and (optionally) upload to Drive."""
        pptx_bytes = await asyncio.to_thread(self._builder.build, title, slides, subtitle)
        logger.info(
            "pptx_built",
            title=title,
            slide_count=len(slides),
            bytes_len=len(pptx_bytes),
        )
        ppt_id = ""
        share_url = ""
        if self._adapter is not None:
            ppt_id, share_url = await self._upload_to_drive(title, pptx_bytes)

        return PPTArtifact(
            ppt_id=ppt_id,
            title=title,
            slides=list(slides),
            share_url=share_url,
        )

    async def build_pptx_bytes(
        self,
        title: str,
        slides: list[SlideSchema],
        subtitle: str = "",
    ) -> bytes:
        """Pure render path: returns deck bytes without any side effect."""
        return await asyncio.to_thread(self._builder.build, title, slides, subtitle)

    async def patch_slide(self, ppt_id: str, page_index: int, slide: SlideSchema) -> None:
        """Per-slide patching is not supported in the python-pptx path.

        Updating a Drive-hosted .pptx in place would require rewriting the
        whole file. Keep the method on the interface for future Feishu native
        Slide API path (Stage 2 decision).
        """
        raise NotImplementedError(
            "per-slide patch requires Feishu native Slides API (deferred to Stage 2)"
        )

    async def _upload_to_drive(self, title: str, pptx_bytes: bytes) -> tuple[str, str]:
        """Upload .pptx bytes to Feishu Drive; return (file_token, share_url)."""
        from typing import Any

        adapter: Any = self._adapter
        file_token: str = await adapter.upload_drive_file(f"{title}.pptx", pptx_bytes)
        if not file_token:
            logger.error("pptx_upload_empty_token", title=title)
            return "", ""
        share_url: str = await adapter.get_share_url(file_token, type_="file")
        await adapter.set_permission_public(file_token, type_="file")
        logger.info("pptx_uploaded", file_token=file_token, share_url=share_url)
        return file_token, share_url
