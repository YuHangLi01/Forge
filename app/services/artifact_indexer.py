"""ArtifactIndexer: write delivered task artifacts back to ChromaDB.

After delivery_node runs, doc sections and PPT slides are indexed with
``source=delivered`` so that future context_retrieval queries can find them.
This closes the loop: outputs become inputs for the next task.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.schemas.artifacts import DocArtifact, PPTArtifact

logger = structlog.get_logger(__name__)

_EMBEDDING_DIM = 768  # bge-base-zh-v1.5


async def _get_embedding(text: str) -> list[float]:
    """Return a text embedding using the project's local bge model."""
    try:
        from app.services.embedding_service import EmbeddingService

        return await EmbeddingService().embed(text)
    except Exception:
        # Fall back to a zero vector when the embedding model is unavailable.
        logger.warning("artifact_indexer_embedding_failed", text_len=len(text))
        return [0.0] * _EMBEDDING_DIM


class ArtifactIndexer:
    """Index delivered artifacts into ChromaDB with ``source=delivered`` metadata.

    All documents are stored under the owning ``user_id`` so the standard
    user-isolation filter in ChromaService continues to protect cross-user data.
    """

    async def index_delivery(
        self,
        *,
        user_id: str,
        task_id: str,
        doc: DocArtifact | None = None,
        ppt: PPTArtifact | None = None,
        task_summary: str = "",
    ) -> None:
        """Write all artifact chunks to ChromaDB.

        Parameters
        ----------
        user_id:
            Owner of the artifact — enforces ChromaDB user isolation.
        task_id:
            Task that produced the artifacts; stored in metadata for retrieval.
        doc:
            DocArtifact produced by feishu_doc_write.
        ppt:
            PPTArtifact produced by feishu_ppt_write.
        task_summary:
            Short summary of the task (used as a top-level searchable chunk).
        """
        if not user_id:
            logger.warning("artifact_indexer_skipped_no_user_id")
            return

        from app.services.chroma_service import ChromaService

        svc = ChromaService()
        chunks: list[tuple[str, str, dict[str, Any]]] = []  # (doc_id, text, metadata)

        base_meta: dict[str, Any] = {
            "source": "delivered",
            "task_id": task_id,
        }

        # Task summary
        if task_summary:
            chunks.append(
                (
                    f"{task_id}:summary",
                    task_summary,
                    {**base_meta, "chunk_type": "task_summary"},
                )
            )

        # Doc sections
        if doc:
            doc_id_val: str = getattr(doc, "doc_id", "") or ""
            doc_title: str = getattr(doc, "title", "") or ""
            for section in getattr(doc, "sections", []) or []:
                sec_id: str = getattr(section, "id", "") or ""
                sec_title: str = getattr(section, "title", "") or ""
                sec_content: str = getattr(section, "content_md", "") or ""
                text = f"{doc_title} > {sec_title}\n\n{sec_content}"
                chunks.append(
                    (
                        f"{task_id}:doc:{sec_id}",
                        text,
                        {
                            **base_meta,
                            "chunk_type": "doc_section",
                            "doc_id": doc_id_val,
                            "doc_title": doc_title,
                            "section_id": sec_id,
                            "section_title": sec_title,
                            "share_url": getattr(doc, "share_url", "") or "",
                        },
                    )
                )

        # PPT slides
        if ppt:
            ppt_id_val: str = getattr(ppt, "ppt_id", "") or ""
            ppt_title: str = getattr(ppt, "title", "") or ""
            for slide in getattr(ppt, "slides", []) or []:
                slide_index: int = getattr(slide, "page_index", 0)
                slide_title: str = getattr(slide, "title", "") or ""
                bullets: list[str] = getattr(slide, "bullets", []) or []
                text = f"{ppt_title} 第{slide_index + 1}页：{slide_title}\n" + "\n".join(
                    f"• {b}" for b in bullets
                )
                chunks.append(
                    (
                        f"{task_id}:ppt:{slide_index}",
                        text,
                        {
                            **base_meta,
                            "chunk_type": "ppt_slide",
                            "ppt_id": ppt_id_val,
                            "ppt_title": ppt_title,
                            "slide_index": slide_index,
                            "slide_title": slide_title,
                            "share_url": getattr(ppt, "share_url", "") or "",
                        },
                    )
                )

        if not chunks:
            logger.info("artifact_indexer_nothing_to_index", task_id=task_id)
            return

        success = 0
        for chunk_id, text, metadata in chunks:
            try:
                embedding = await _get_embedding(text)
                await svc.add(
                    user_id=user_id,
                    doc_id=chunk_id,
                    text=text,
                    embedding=embedding,
                    metadata=metadata,
                )
                success += 1
            except Exception:
                logger.exception("artifact_indexer_chunk_failed", chunk_id=chunk_id)

        logger.info(
            "artifact_indexer_done",
            task_id=task_id,
            total=len(chunks),
            success=success,
        )
