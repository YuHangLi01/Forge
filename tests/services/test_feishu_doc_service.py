"""Coverage tests for FeishuDocService.patch_section paths."""

from __future__ import annotations

import pytest


def _make_adapter_mock(blocks=None, delete_raises=False):
    from unittest.mock import AsyncMock, MagicMock

    adapter = MagicMock()
    adapter.get_document_blocks = AsyncMock(return_value=blocks or [])
    del_side_effect = RuntimeError("del failed") if delete_raises else None
    adapter.delete_blocks = AsyncMock(side_effect=del_side_effect)
    adapter.batch_update_blocks = AsyncMock(return_value=["b_new"])
    return adapter


class TestPatchSection:
    @pytest.mark.asyncio
    async def test_no_section_block_ids_returns_early(self) -> None:
        from app.services.feishu_doc_service import FeishuDocService

        adapter = _make_adapter_mock()
        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", [], "Title", "New content")
        adapter.get_document_blocks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_blocks_returns_early(self) -> None:
        from app.services.feishu_doc_service import FeishuDocService

        adapter = _make_adapter_mock(blocks=[])
        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", ["h1", "b1"], "Title", "New content")
        adapter.delete_blocks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_only_heading_no_body_blocks(self) -> None:
        """section_block_ids has only heading — no delete needed, just insert."""
        from app.services.feishu_doc_service import FeishuDocService

        blocks = [
            {"block_id": "page", "block_type": 1},
            {"block_id": "h1_blk", "block_type": 3},
        ]
        adapter = _make_adapter_mock(blocks=blocks)
        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", ["h1_blk"], "Title", "New content")
        adapter.delete_blocks.assert_not_awaited()
        adapter.batch_update_blocks.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_heading_not_found_inserts_at_minus1(self) -> None:
        """Heading block not in page children → insert_index = -1."""
        from app.services.feishu_doc_service import FeishuDocService

        blocks = [
            {"block_id": "page", "block_type": 1},
            {"block_id": "other_blk", "block_type": 2},
        ]
        adapter = _make_adapter_mock(blocks=blocks)
        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", ["h_blk", "b1"], "Title", "New content")
        adapter.batch_update_blocks.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_exception_returns_early(self) -> None:
        """Delete failure should abort before insert."""
        from app.services.feishu_doc_service import FeishuDocService

        blocks = [
            {"block_id": "page", "block_type": 1},
            {"block_id": "h1_blk", "block_type": 3},
            {"block_id": "body_blk", "block_type": 2},
        ]
        adapter = _make_adapter_mock(blocks=blocks, delete_raises=True)
        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", ["h1_blk", "body_blk"], "Title", "New content")
        adapter.delete_blocks.assert_awaited_once()
        adapter.batch_update_blocks.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insert_exception_logged(self) -> None:
        """Insert failure should be caught and logged."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.feishu_doc_service import FeishuDocService

        blocks = [
            {"block_id": "page", "block_type": 1},
            {"block_id": "h1_blk", "block_type": 3},
        ]
        adapter = MagicMock()
        adapter.get_document_blocks = AsyncMock(return_value=blocks)
        adapter.delete_blocks = AsyncMock()
        adapter.batch_update_blocks = AsyncMock(side_effect=RuntimeError("insert failed"))

        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", ["h1_blk"], "Title", "New content")
        adapter.batch_update_blocks.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_full_path_success(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.services.feishu_doc_service import FeishuDocService

        blocks = [
            {"block_id": "page", "block_type": 1},
            {"block_id": "h1_blk", "block_type": 3},
            {"block_id": "body1", "block_type": 2},
            {"block_id": "body2", "block_type": 2},
        ]
        adapter = MagicMock()
        adapter.get_document_blocks = AsyncMock(return_value=blocks)
        adapter.delete_blocks = AsyncMock()
        adapter.batch_update_blocks = AsyncMock(return_value=["new1", "new2"])

        svc = FeishuDocService(adapter=adapter)
        await svc.patch_section("doc1", ["h1_blk", "body1", "body2"], "背景", "## 新背景\n内容")
        adapter.delete_blocks.assert_awaited_once_with("doc1", ["body1", "body2"])
        adapter.batch_update_blocks.assert_awaited_once()
