from __future__ import annotations

import structlog

from app.converters.md2feishu import md_to_feishu_blocks
from app.converters.simple_md import md_to_simple_blocks
from app.integrations.feishu.adapter import FeishuAdapter
from app.schemas.artifacts import DocArtifact, DocSection

logger = structlog.get_logger(__name__)


class FeishuDocService:
    def __init__(self, adapter: FeishuAdapter | None = None) -> None:
        self._adapter = adapter or FeishuAdapter()

    async def create_from_markdown(
        self,
        title: str,
        markdown: str,
        folder_token: str = "",
        simple: bool = False,
    ) -> DocArtifact:
        """Create a Feishu Doc and write the markdown into it.

        ``simple=True`` uses ``md_to_simple_blocks`` — a minimal converter
        that only emits heading/paragraph/bullet blocks with plain text
        runs. This sidesteps schema-validation surprises in the richer
        ``md_to_feishu_blocks`` path while we finish auditing docx v1
        block schemas. Demo / production paths default to ``simple=True``;
        callers that want bold/code/tables/links can opt into the
        rich converter explicitly.
        """
        doc_token = await self._adapter.create_document(title, folder_token)
        logger.info("doc_created", doc_token=doc_token, title=title)

        children = (
            md_to_simple_blocks(markdown)
            if simple
            else md_to_feishu_blocks(markdown, parent_block_id=doc_token)
        )
        block_ids = await self._adapter.batch_update_blocks(doc_token, children)
        logger.info(
            "blocks_written",
            doc_token=doc_token,
            block_count=len(block_ids),
            converter="simple" if simple else "rich",
        )

        all_blocks = await self._adapter.get_document_blocks(doc_token)
        sections = self._align_sections(markdown, all_blocks)

        share_url = await self._adapter.get_share_url(doc_token, "doc")

        return DocArtifact(
            doc_id=doc_token,
            title=title,
            sections=sections,
            share_url=share_url,
        )

    def _align_sections(self, markdown: str, blocks: list[dict[str, object]]) -> list[DocSection]:
        from app.converters import feishu_block_types as bt

        # Parse H1 boundaries from markdown
        section_titles: list[str] = []
        section_contents: list[list[str]] = []
        current_title = ""
        current_lines: list[str] = []

        for line in markdown.splitlines():
            if line.startswith("# "):
                if current_title:
                    section_titles.append(current_title)
                    section_contents.append(current_lines)
                current_title = line[2:].strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_title:
            section_titles.append(current_title)
            section_contents.append(current_lines)

        if not section_titles:
            return []

        # Positional match: Nth HEADING1 block in Feishu response → Nth H1 section
        h1_positions = [i for i, blk in enumerate(blocks) if blk.get("block_type") == bt.HEADING1]

        sections: list[DocSection] = []
        for idx, title in enumerate(section_titles):
            if idx < len(h1_positions):
                start = h1_positions[idx]
                end = h1_positions[idx + 1] if idx + 1 < len(h1_positions) else len(blocks)
                section_block_ids = [
                    str(blocks[i]["block_id"]) for i in range(start, end) if "block_id" in blocks[i]
                ]
            else:
                section_block_ids = []

            sections.append(
                DocSection(
                    id=f"section_{idx}",
                    title=title,
                    content_md="\n".join(section_contents[idx]),
                    block_ids=section_block_ids,
                )
            )

        return sections

    async def patch_section(
        self,
        doc_id: str,
        section_block_ids: list[str],
        section_title: str,
        new_content_md: str,
    ) -> None:
        """Replace a section's content blocks in-place using delete-then-insert.

        Deletes the non-heading blocks from section_block_ids[1:] (keeps the
        heading block at [0]), then appends new blocks under the heading.
        Falls back gracefully if block operations fail.
        """
        if not section_block_ids:
            logger.warning("patch_section_no_block_ids", section=section_title)
            return

        heading_block_id = section_block_ids[0]
        body_block_ids = section_block_ids[1:]

        # Delete old body blocks
        if body_block_ids:
            try:
                await self._adapter.delete_blocks(doc_id, body_block_ids)
                logger.debug(
                    "patch_section_deleted", n_blocks=len(body_block_ids), section=section_title
                )
            except Exception:
                logger.exception("patch_section_delete_failed", section=section_title)
                return

        # Insert new content under the heading block
        new_blocks = md_to_simple_blocks(new_content_md)
        if new_blocks:
            try:
                await self._adapter.batch_update_blocks(
                    doc_id, new_blocks, parent_block_id=heading_block_id
                )
                logger.info(
                    "patch_section_inserted",
                    section=section_title,
                    n_blocks=len(new_blocks),
                )
            except Exception:
                logger.exception("patch_section_insert_failed", section=section_title)
