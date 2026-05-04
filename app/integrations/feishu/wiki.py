"""Feishu Wiki (knowledge base) client — archival of delivered task artifacts."""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


class WikiArchiveError(Exception):
    """Raised when a Feishu Wiki API call fails."""


class FeishuWikiClient:
    """Create wiki nodes under a configured space, used for delivery archival.

    Requires ``FEISHU_WIKI_SPACE_ID`` in settings.  When the space ID is empty
    the client is a no-op so the demo can run without wiki credentials.
    """

    def __init__(self) -> None:
        import lark_oapi as lark

        from app.config import get_settings

        settings = get_settings()
        self._space_id: str = settings.FEISHU_WIKI_SPACE_ID
        self._parent_node_token: str = settings.FEISHU_WIKI_PARENT_NODE_TOKEN
        self._client = (
            lark.Client.builder()
            .app_id(settings.FEISHU_APP_ID)
            .app_secret(settings.FEISHU_APP_SECRET)
            .build()
        )

    async def create_node(
        self,
        title: str,
        doc_token: str | None = None,
    ) -> str | None:
        """Create a wiki node under the configured space.

        Parameters
        ----------
        title:
            Node title shown in the wiki tree.
        doc_token:
            If provided, links an existing Feishu Doc into the wiki tree
            (creates a shortcut node); otherwise creates a blank wiki page.

        Returns
        -------
        str | None
            The ``node_token`` of the created wiki node, or ``None`` if
            ``FEISHU_WIKI_SPACE_ID`` is not configured.
        """
        if not self._space_id:
            logger.debug("wiki_create_node_skipped_no_space_id")
            return None

        try:
            import lark_oapi as lark

            body: dict[str, object] = {
                "obj_type": "doc",
                "title": title,
            }
            if self._parent_node_token:
                body["parent_node_token"] = self._parent_node_token
            if doc_token:
                body["obj_token"] = doc_token

            def _create() -> lark.BaseResponse:  # type: ignore[name-defined]
                return self._client.request(  # type: ignore[no-any-return]
                    "POST",
                    f"/open-apis/wiki/v2/spaces/{self._space_id}/nodes",
                    body,
                )

            resp = await asyncio.to_thread(_create)

            if not getattr(resp, "success", lambda: False)():
                code = getattr(resp, "code", "?")
                msg = getattr(resp, "msg", "?")
                raise WikiArchiveError(f"wiki create_node failed: code={code} msg={msg}")

            data = getattr(resp, "data", {}) or {}
            node = data.get("node") or {}
            node_token: str = node.get("node_token", "")
            logger.info("wiki_node_created", title=title, node_token=node_token)
            return node_token

        except WikiArchiveError:
            raise
        except Exception as exc:
            raise WikiArchiveError(f"wiki API error: {exc}") from exc

    def share_url(self, node_token: str) -> str:
        """Return a shareable wiki URL for the given node_token."""
        return f"https://feishu.cn/wiki/{node_token}"
