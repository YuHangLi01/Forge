import structlog

from app.converters.md2feishu import md_to_feishu_blocks
from app.integrations.feishu.adapter import FeishuAdapter
from app.schemas.artifacts import DocArtifact, DocSection

logger = structlog.get_logger(__name__)


class FeishuDocService:
    def __init__(self, adapter: FeishuAdapter | None = None) -> None:
        self._adapter = adapter or FeishuAdapter()

    async def create_from_markdown(
        self, title: str, markdown: str, folder_token: str = ""
    ) -> DocArtifact:
        doc_token = await self._adapter.create_document(title, folder_token)
        logger.info("doc_created", doc_token=doc_token, title=title)

        requests = md_to_feishu_blocks(markdown, parent_block_id=doc_token)
        block_ids = await self._adapter.batch_update_blocks(doc_token, requests)
        logger.info("blocks_written", doc_token=doc_token, block_count=len(block_ids))

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
        sections: list[DocSection] = []
        current_title = ""
        current_lines: list[str] = []
        current_block_ids: list[str] = []

        for line in markdown.splitlines():
            if line.startswith("# "):
                if current_title:
                    sections.append(
                        DocSection(
                            id=f"section_{len(sections)}",
                            title=current_title,
                            content_md="\n".join(current_lines),
                            block_ids=current_block_ids,
                        )
                    )
                current_title = line[2:].strip()
                current_lines = []
                current_block_ids = []
            else:
                current_lines.append(line)

        if current_title:
            sections.append(
                DocSection(
                    id=f"section_{len(sections)}",
                    title=current_title,
                    content_md="\n".join(current_lines),
                    block_ids=current_block_ids,
                )
            )

        _ = blocks  # block_id alignment requires Feishu block position API (T10 follow-up)
        return sections
