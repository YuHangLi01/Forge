"""Unit tests for FeishuDocService.

The service is async glue around FeishuAdapter (which speaks lark-oapi
under the hood). All adapter methods get AsyncMock'd so the test stays
fully offline. md_to_feishu_blocks is real — those tests live in
tests/converters/.
"""

from unittest.mock import AsyncMock

import pytest

from app.schemas.artifacts import DocArtifact
from app.services.feishu_doc_service import FeishuDocService


@pytest.mark.asyncio
async def test_create_from_markdown_happy_path() -> None:
    adapter = AsyncMock()
    adapter.create_document.return_value = "doc-token-123"
    adapter.batch_update_blocks.return_value = ["blk-1", "blk-2", "blk-3"]
    adapter.get_document_blocks.return_value = [
        {"block_id": "blk-1", "block_type": 3},
        {"block_id": "blk-2", "block_type": 2},
        {"block_id": "blk-3", "block_type": 12},
    ]
    adapter.get_share_url.return_value = "https://open.feishu.cn/docx/doc-token-123"

    md = "# 标题\n\n正文段落。\n\n- 要点 A\n- 要点 B\n"
    artifact = await FeishuDocService(adapter).create_from_markdown("测试文档", md, simple=True)

    assert isinstance(artifact, DocArtifact)
    assert artifact.doc_id == "doc-token-123"
    assert artifact.title == "测试文档"
    assert artifact.share_url == "https://open.feishu.cn/docx/doc-token-123"
    adapter.create_document.assert_awaited_once_with("测试文档", "")
    adapter.batch_update_blocks.assert_awaited_once()
    args, _ = adapter.batch_update_blocks.await_args
    assert args[0] == "doc-token-123"
    assert isinstance(args[1], list)
    assert len(args[1]) >= 1


@pytest.mark.asyncio
async def test_sections_split_by_h1() -> None:
    """A markdown with 3 H1 sections should produce 3 DocSection entries."""
    adapter = AsyncMock()
    adapter.create_document.return_value = "tok"
    adapter.batch_update_blocks.return_value = []
    adapter.get_document_blocks.return_value = []
    adapter.get_share_url.return_value = "x"

    md = "# 第一节\n正文1\n\n# 第二节\n正文2\n\n# 第三节\n正文3\n"
    artifact = await FeishuDocService(adapter).create_from_markdown("Doc", md)
    titles = [s.title for s in artifact.sections]
    assert titles == ["第一节", "第二节", "第三节"]


@pytest.mark.asyncio
async def test_create_from_markdown_propagates_adapter_error() -> None:
    adapter = AsyncMock()
    adapter.create_document.side_effect = RuntimeError("API down")

    with pytest.raises(RuntimeError, match="API down"):
        await FeishuDocService(adapter).create_from_markdown("X", "# Y")


@pytest.mark.asyncio
async def test_folder_token_is_forwarded() -> None:
    adapter = AsyncMock()
    adapter.create_document.return_value = "tok"
    adapter.batch_update_blocks.return_value = []
    adapter.get_document_blocks.return_value = []
    adapter.get_share_url.return_value = ""

    await FeishuDocService(adapter).create_from_markdown("X", "# Y", folder_token="folder-7")
    adapter.create_document.assert_awaited_once_with("X", "folder-7")


@pytest.mark.asyncio
async def test_no_h1_returns_empty_sections() -> None:
    adapter = AsyncMock()
    adapter.create_document.return_value = "tok"
    adapter.batch_update_blocks.return_value = []
    adapter.get_document_blocks.return_value = []
    adapter.get_share_url.return_value = ""

    md = "正文1\n正文2\n## 二级标题不算节\n"
    artifact = await FeishuDocService(adapter).create_from_markdown("X", md)
    assert artifact.sections == []
