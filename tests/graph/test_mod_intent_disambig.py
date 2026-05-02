"""Tests for cross-product modification disambiguation (S3-T11)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.artifacts import DocArtifact, DocSection, PPTArtifact, SlideSchema
from app.schemas.enums import ModificationType, ScopeType, SlideLayout
from app.schemas.intent import ModificationIntent


def _doc() -> DocArtifact:
    return DocArtifact(
        doc_id="doc-001",
        title="产品复盘",
        sections=[
            DocSection(id="s1", title="背景", content_md="背景内容"),
            DocSection(id="s2", title="结论", content_md="结论内容"),
        ],
        share_url="https://feishu.test/doc",
    )


def _ppt() -> PPTArtifact:
    slides = [
        SlideSchema(
            page_index=i,
            layout=SlideLayout.title_content,
            title=f"第{i + 1}页",
            bullets=[],
            speaker_notes="",
        )
        for i in range(3)
    ]
    return PPTArtifact(
        ppt_id="ppt-001", title="演示文稿", slides=slides, share_url="https://feishu.test/ppt"
    )


def _mod_intent(target: str = "document") -> ModificationIntent:
    return ModificationIntent(
        target=target,  # type: ignore[arg-type]
        scope_type=ScopeType.specific_section,
        scope_identifier="背景",
        modification_type=ModificationType.rewrite,
        instruction="请改写得更简洁",
        ambiguity_high=False,
    )


def _base_state(doc: DocArtifact | None = None, ppt: PPTArtifact | None = None) -> dict:
    return {
        "message_id": "msg_test",
        "user_id": "usr_test",
        "chat_id": "chat_test",
        "normalized_text": "改一下第2节",
        "doc": doc,
        "ppt": ppt,
        "modification_history": [],
        "completed_steps": [],
        "pending_user_action": None,
    }


# ── keyword_disambiguate unit tests ───────────────────────────────────────────


def test_keyword_disambiguate_doc_keyword() -> None:
    from app.graph.nodes.mod_intent_parser import _keyword_disambiguate

    assert _keyword_disambiguate("改一下第三章节") == "document"
    assert _keyword_disambiguate("文档的第一节要改") == "document"


def test_keyword_disambiguate_ppt_keyword() -> None:
    from app.graph.nodes.mod_intent_parser import _keyword_disambiguate

    assert _keyword_disambiguate("把第2页改成英文") == "presentation"
    assert _keyword_disambiguate("幻灯片的标题要更改") == "presentation"
    assert _keyword_disambiguate("PPT第三张") == "presentation"


def test_keyword_disambiguate_ambiguous_returns_none() -> None:
    from app.graph.nodes.mod_intent_parser import _keyword_disambiguate

    assert _keyword_disambiguate("改一下第2个") is None
    assert _keyword_disambiguate("那个要修改") is None


# ── doc-only: no ambiguity ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_doc_only_no_ambiguity() -> None:
    """Doc only → target forced to 'document', no clarify card."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    fake_intent = _mod_intent("presentation")  # LLM might guess wrong

    state = _base_state(doc=_doc(), ppt=None)
    state["normalized_text"] = "改一下第2节文字"

    with patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock:
        mock.return_value = fake_intent
        result = await mod_intent_parser_node(state)

    assert "mod_intent" in result
    assert result["mod_intent"].target == "document"
    assert "pending_user_action" not in result or result.get("pending_user_action") is None


@pytest.mark.asyncio
async def test_ppt_only_no_ambiguity() -> None:
    """PPT only → target forced to 'presentation', no clarify card."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    fake_intent = _mod_intent("document")  # LLM might guess wrong

    state = _base_state(doc=None, ppt=_ppt())
    state["normalized_text"] = "把第2页改成中文"

    with patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock:
        mock.return_value = fake_intent
        result = await mod_intent_parser_node(state)

    assert "mod_intent" in result
    assert result["mod_intent"].target == "presentation"


# ── doc+ppt: keyword disambiguation ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_doc_keyword_disambiguation() -> None:
    """'文档' keyword → target forced to document even when both exist."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    fake_intent = _mod_intent("presentation")  # LLM might guess wrong

    state = _base_state(doc=_doc(), ppt=_ppt())
    state["normalized_text"] = "帮我改一下文档的第2节"

    with patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock:
        mock.return_value = fake_intent
        result = await mod_intent_parser_node(state)

    assert result.get("mod_intent") is not None
    assert result["mod_intent"].target == "document"


@pytest.mark.asyncio
async def test_ppt_keyword_disambiguation() -> None:
    """'幻灯片' keyword → target forced to presentation even when both exist."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    fake_intent = _mod_intent("document")  # LLM might guess wrong

    state = _base_state(doc=_doc(), ppt=_ppt())
    state["normalized_text"] = "把幻灯片第3页改成英文"

    with patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock:
        mock.return_value = fake_intent
        result = await mod_intent_parser_node(state)

    assert result.get("mod_intent") is not None
    assert result["mod_intent"].target == "presentation"


# ── history-based disambiguation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_history_based_disambiguation() -> None:
    """Ambiguous text + history → use last target from history."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    history_record = MagicMock()
    history_record.scope_identifier = "背景"
    history_record.instruction = "改写"
    history_record.target = "presentation"

    fake_intent = _mod_intent("document")

    state = _base_state(doc=_doc(), ppt=_ppt())
    state["normalized_text"] = "改一下那个"
    state["modification_history"] = [history_record]

    with patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock:
        mock.return_value = fake_intent
        result = await mod_intent_parser_node(state)

    assert result.get("mod_intent") is not None
    assert result["mod_intent"].target == "presentation"


# ── truly ambiguous: triggers clarify card ───────────────────────────────────


@pytest.mark.asyncio
async def test_truly_ambiguous_triggers_clarify() -> None:
    """Ambiguous text + no history + LLM says ambiguity_high → clarify card emitted."""
    from app.graph.nodes.mod_intent_parser import mod_intent_parser_node

    ambiguous_intent = ModificationIntent(
        target="document",
        scope_type=ScopeType.specific_section,
        scope_identifier="第2部分",
        modification_type=ModificationType.rewrite,
        instruction="改一下",
        ambiguity_high=True,
    )

    state = _base_state(doc=_doc(), ppt=_ppt())
    state["normalized_text"] = "改一下第2个"

    with (
        patch("app.services.llm_service.LLMService.structured", new_callable=AsyncMock) as mock,
        patch("app.integrations.feishu.adapter.FeishuAdapter") as MockAdapter,
    ):
        mock.return_value = ambiguous_intent
        mock_inst = AsyncMock()
        MockAdapter.return_value = mock_inst

        result = await mod_intent_parser_node(state)

    mock_inst.reply_card.assert_awaited_once()
    assert "pending_user_action" in result
    assert result["pending_user_action"]["kind"] == "mod_target_clarify"
    assert "mod_intent" not in result or result.get("mod_intent") is None
