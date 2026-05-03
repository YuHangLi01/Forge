"""Coverage tests for PPTService — upload path and edge cases."""

from __future__ import annotations

import pytest

from app.schemas.artifacts import SlideSchema
from app.schemas.enums import SlideLayout


def _make_slides(n: int = 2) -> list[SlideSchema]:
    return [
        SlideSchema(
            page_index=i,
            layout=SlideLayout.title_content,
            title=f"Slide {i}",
            bullets=[f"Bullet {i}"],
        )
        for i in range(n)
    ]


class TestPPTService:
    @pytest.mark.asyncio
    async def test_create_without_adapter_returns_artifact(self) -> None:
        from app.services.ppt_service import PPTService

        svc = PPTService()
        result = await svc.create_from_outline("Test Deck", _make_slides())
        assert result.ppt_id == ""
        assert result.title == "Test Deck"
        assert len(result.slides) == 2

    @pytest.mark.asyncio
    async def test_create_with_adapter_calls_upload(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.services.ppt_service import PPTService

        mock_adapter = MagicMock()
        mock_adapter.upload_drive_file = AsyncMock(return_value="file_tok_123")
        mock_adapter.get_share_url = AsyncMock(return_value="https://example.com/share")
        mock_adapter.set_permission_public = AsyncMock()

        svc = PPTService(adapter=mock_adapter)
        result = await svc.create_from_outline("Upload Deck", _make_slides())
        assert result.ppt_id == "file_tok_123"
        assert result.share_url == "https://example.com/share"
        mock_adapter.upload_drive_file.assert_awaited_once()
        mock_adapter.set_permission_public.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_empty_token_returns_empty(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.services.ppt_service import PPTService

        mock_adapter = MagicMock()
        mock_adapter.upload_drive_file = AsyncMock(return_value="")  # empty token
        mock_adapter.get_share_url = AsyncMock()
        mock_adapter.set_permission_public = AsyncMock()

        svc = PPTService(adapter=mock_adapter)
        result = await svc.create_from_outline("Empty Token Deck", _make_slides())
        assert result.ppt_id == ""
        assert result.share_url == ""
        mock_adapter.get_share_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_pptx_bytes_returns_bytes(self) -> None:
        from app.services.ppt_service import PPTService

        svc = PPTService()
        data = await svc.build_pptx_bytes("Bytes Deck", _make_slides())
        assert isinstance(data, bytes)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_patch_slide_raises(self) -> None:
        from app.services.ppt_service import PPTService

        svc = PPTService()
        with pytest.raises(NotImplementedError):
            await svc.patch_slide("ppt1", 0, _make_slides(1)[0])
