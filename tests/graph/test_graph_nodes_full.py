"""Coverage tests for clarify_question, error_handler, preprocess, doc_section_editor."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── error_handler_node ────────────────────────────────────────────────────────


class TestErrorHandlerNode:
    @pytest.mark.asyncio
    async def test_failed_status_default_message(self) -> None:
        from app.graph.nodes.error_handler import error_handler_node
        from app.schemas.enums import TaskStatus

        with patch("app.graph.nodes.error_handler.ProgressBroadcaster") as mock_pb_cls:
            mock_pb = MagicMock()
            mock_pb.emit_error = MagicMock()
            mock_pb_cls.return_value = mock_pb
            result = await error_handler_node({"message_id": "m1", "status": TaskStatus.failed})

        mock_pb.emit_error.assert_called_once()
        assert "错误" in mock_pb.emit_error.call_args[0][0]
        assert result["status"] == TaskStatus.completed

    @pytest.mark.asyncio
    async def test_cancelled_status_custom_message(self) -> None:
        from app.graph.nodes.error_handler import error_handler_node
        from app.schemas.enums import TaskStatus

        with patch("app.graph.nodes.error_handler.ProgressBroadcaster") as mock_pb_cls:
            mock_pb = MagicMock()
            mock_pb.emit_error = MagicMock()
            mock_pb_cls.return_value = mock_pb
            result = await error_handler_node(
                {"message_id": "m1", "status": TaskStatus.cancelled, "error": "用户取消"}
            )

        mock_pb.emit_error.assert_called_once_with("用户取消")
        assert result["status"] == TaskStatus.completed

    @pytest.mark.asyncio
    async def test_empty_error_uses_default(self) -> None:
        from app.graph.nodes.error_handler import error_handler_node

        with patch("app.graph.nodes.error_handler.ProgressBroadcaster") as mock_pb_cls:
            mock_pb = MagicMock()
            mock_pb.emit_error = MagicMock()
            mock_pb_cls.return_value = mock_pb
            await error_handler_node({"message_id": "m1", "error": "", "status": None})

        called_with = mock_pb.emit_error.call_args[0][0]
        assert called_with  # non-empty default

    @pytest.mark.asyncio
    async def test_no_message_id(self) -> None:
        from app.graph.nodes.error_handler import error_handler_node
        from app.schemas.enums import TaskStatus

        with patch("app.graph.nodes.error_handler.ProgressBroadcaster") as mock_pb_cls:
            mock_pb = MagicMock()
            mock_pb_cls.return_value = mock_pb
            result = await error_handler_node({})
        assert result["status"] == TaskStatus.completed


# ── clarify_question_node ─────────────────────────────────────────────────────


def _make_clarify_state(**overrides: object) -> dict:
    base = {
        "chat_id": "c1",
        "message_id": "m1",
        "normalized_text": "帮我做个PPT",
        "intent": None,
    }
    base.update(overrides)
    return base


class TestClarifyQuestionNode:
    @pytest.mark.asyncio
    async def test_normal_flow_card_sent(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_llm.return_value = "问题1\n问题2"
            mock_feishu = AsyncMock()
            mock_adapter_cls.return_value = mock_feishu

            result = await clarify_question_node(_make_clarify_state())

        assert "pending_user_action" in result
        assert result["pending_user_action"]["kind"] == "clarify"
        assert result.get("clarify_count") == 1

    @pytest.mark.asyncio
    async def test_llm_failure_uses_fallback_questions(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.llm_service.LLMService.invoke",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM down"),
            ),
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_adapter_cls.return_value = AsyncMock()
            result = await clarify_question_node(_make_clarify_state())

        assert result["pending_user_action"]["kind"] == "clarify"

    @pytest.mark.asyncio
    async def test_no_message_id_uses_send_text(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_llm.return_value = "问题1"
            mock_feishu = AsyncMock()
            mock_adapter_cls.return_value = mock_feishu
            result = await clarify_question_node(_make_clarify_state(message_id="", chat_id="c1"))

        assert result["pending_user_action"]

    @pytest.mark.asyncio
    async def test_redis_failure_still_returns(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("redis.asyncio.from_url", side_effect=Exception("redis down")),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_llm.return_value = "问题1\n问题2"
            mock_adapter_cls.return_value = AsyncMock()
            result = await clarify_question_node(_make_clarify_state())

        assert "pending_user_action" in result

    @pytest.mark.asyncio
    async def test_feishu_exception_does_not_raise(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_llm.return_value = "问题1"
            mock_feishu = AsyncMock()
            mock_feishu.reply_card = AsyncMock(side_effect=Exception("feishu error"))
            mock_adapter_cls.return_value = mock_feishu
            result = await clarify_question_node(_make_clarify_state())

        assert "pending_user_action" in result

    @pytest.mark.asyncio
    async def test_intent_summary_included(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node
        from app.schemas.intent import IntentSchema

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        intent = IntentSchema(
            task_type="create_new",
            primary_goal="生成文档",
            output_formats=["document"],
            ambiguity_score=0.5,
        )

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_llm.return_value = "问题"
            mock_adapter_cls.return_value = AsyncMock()
            result = await clarify_question_node(_make_clarify_state(intent=intent))

        assert result["clarify_count"] == 1

    @pytest.mark.asyncio
    async def test_increments_clarify_count(self) -> None:
        from app.graph.nodes.clarify_question import clarify_question_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
        ):
            mock_llm.return_value = "问题"
            mock_adapter_cls.return_value = AsyncMock()
            result = await clarify_question_node(_make_clarify_state(clarify_count=2))

        assert result["clarify_count"] == 3


# ── preprocess_node ───────────────────────────────────────────────────────────


class TestPreprocessNode:
    @pytest.mark.asyncio
    async def test_plain_text(self) -> None:
        from app.graph.nodes.preprocess import preprocess_node

        with patch("app.graph.nodes.preprocess.ProgressBroadcaster"):
            result = await preprocess_node(
                {"raw_input": "帮我写PPT", "attachments": [], "message_id": "m1", "chat_id": "c1"}
            )
        assert result["normalized_text"] == "帮我写PPT"

    @pytest.mark.asyncio
    async def test_empty_text_raises(self) -> None:
        from app.exceptions import ForgeError
        from app.graph.nodes.preprocess import preprocess_node

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            pytest.raises(ForgeError),
        ):
            await preprocess_node(
                {"raw_input": "  ", "attachments": [], "message_id": "m1", "chat_id": "c1"}
            )

    @pytest.mark.asyncio
    async def test_cancel_phrase(self) -> None:
        from app.graph.nodes.preprocess import preprocess_node
        from app.schemas.enums import TaskStatus

        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=None)
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            patch("redis.asyncio.from_url", return_value=mock_r),
        ):
            result = await preprocess_node(
                {"raw_input": "取消", "attachments": [], "message_id": "m1", "chat_id": "c1"}
            )
        assert result["status"] == TaskStatus.cancelled

    @pytest.mark.asyncio
    async def test_cancel_phrase_no_active_task(self) -> None:
        from app.graph.nodes.preprocess import preprocess_node

        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=None)
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            patch("redis.asyncio.from_url", return_value=mock_r),
        ):
            result = await preprocess_node(
                {"raw_input": "cancel", "attachments": [], "message_id": "m1", "chat_id": "c1"}
            )
        assert result.get("normalized_text") == "cancel"

    @pytest.mark.asyncio
    async def test_unsupported_attachment(self) -> None:
        from app.exceptions import ForgeError
        from app.graph.nodes.preprocess import preprocess_node

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            pytest.raises(ForgeError) as exc_info,
        ):
            await preprocess_node(
                {
                    "raw_input": "",
                    "attachments": [{"type": "image", "file_key": "k1"}],
                    "message_id": "m1",
                    "chat_id": "c1",
                }
            )
        assert exc_info.value.code == 415

    @pytest.mark.asyncio
    async def test_audio_attachment(self) -> None:
        from app.graph.nodes.preprocess import preprocess_node

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
            patch("app.services.asr_service.ASRService") as mock_asr_cls,
        ):
            mock_asr = AsyncMock()
            mock_asr.transcribe_voice_message = AsyncMock(return_value="语音转文字结果")
            mock_asr_cls.return_value = mock_asr
            result = await preprocess_node(
                {
                    "raw_input": "",
                    "attachments": [{"type": "audio", "file_key": "k1"}],
                    "message_id": "m1",
                    "chat_id": "c1",
                }
            )
        assert result["normalized_text"] == "语音转文字结果"

    @pytest.mark.asyncio
    async def test_audio_empty_result_raises(self) -> None:
        from app.exceptions import ForgeError
        from app.graph.nodes.preprocess import preprocess_node

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
            patch("app.services.asr_service.ASRService") as mock_asr_cls,
        ):
            mock_asr = AsyncMock()
            mock_asr.transcribe_voice_message = AsyncMock(return_value="")
            mock_asr_cls.return_value = mock_asr
            with pytest.raises(ForgeError):
                await preprocess_node(
                    {
                        "raw_input": "",
                        "attachments": [{"type": "audio", "file_key": "k1"}],
                        "message_id": "m1",
                        "chat_id": "c1",
                    }
                )

    @pytest.mark.asyncio
    async def test_file_attachment(self) -> None:
        from app.graph.nodes.preprocess import preprocess_node

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
            patch("app.services.file_extractor.extract_text_from_file") as mock_extract,
        ):
            mock_feishu = AsyncMock()
            mock_feishu.download_message_resource = AsyncMock(return_value=b"file data")
            mock_adapter_cls.return_value = mock_feishu
            mock_extract.return_value = "extracted text"
            result = await preprocess_node(
                {
                    "raw_input": "",
                    "attachments": [{"type": "file", "file_key": "k1", "file_name": "doc.txt"}],
                    "message_id": "m1",
                    "chat_id": "c1",
                }
            )
        assert result["normalized_text"] == "extracted text"

    @pytest.mark.asyncio
    async def test_file_empty_content_raises(self) -> None:
        from app.exceptions import ForgeError
        from app.graph.nodes.preprocess import preprocess_node

        with (
            patch("app.graph.nodes.preprocess.ProgressBroadcaster"),
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_adapter_cls,
            patch("app.services.file_extractor.extract_text_from_file") as mock_extract,
        ):
            mock_feishu = AsyncMock()
            mock_feishu.download_message_resource = AsyncMock(return_value=b"")
            mock_adapter_cls.return_value = mock_feishu
            mock_extract.return_value = "   "
            with pytest.raises(ForgeError):
                await preprocess_node(
                    {
                        "raw_input": "",
                        "attachments": [{"type": "file", "file_key": "k1"}],
                        "message_id": "m1",
                        "chat_id": "c1",
                    }
                )


# ── _try_cancel_active_task ───────────────────────────────────────────────────


class TestTryCancelActiveTask:
    @pytest.mark.asyncio
    async def test_no_chat_id_returns(self) -> None:
        from app.graph.nodes.preprocess import _try_cancel_active_task

        await _try_cancel_active_task("", "m1")

    @pytest.mark.asyncio
    async def test_no_active_task_returns(self) -> None:
        from app.graph.nodes.preprocess import _try_cancel_active_task

        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=None)
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with patch("redis.asyncio.from_url", return_value=mock_r):
            await _try_cancel_active_task("chat1", "m1")

    @pytest.mark.asyncio
    async def test_same_thread_returns(self) -> None:
        from app.graph.nodes.preprocess import _try_cancel_active_task

        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=b"m1")
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with patch("redis.asyncio.from_url", return_value=mock_r):
            await _try_cancel_active_task("chat1", "m1")

    @pytest.mark.asyncio
    async def test_different_thread_cancels(self) -> None:
        from app.graph.nodes.preprocess import _try_cancel_active_task

        mock_r = AsyncMock()
        mock_r.get = AsyncMock(return_value=b"other_thread")
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        mock_graph = AsyncMock()
        mock_graph.aupdate_state = AsyncMock()

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.graph.get_or_init_graph", return_value=mock_graph),
            patch("app.tasks.message_tasks.resume_graph_task") as mock_resume,
        ):
            mock_resume.delay = MagicMock()
            await _try_cancel_active_task("chat1", "m1")

        mock_graph.aupdate_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_is_logged(self) -> None:
        from app.graph.nodes.preprocess import _try_cancel_active_task

        with patch("redis.asyncio.from_url", side_effect=Exception("redis down")):
            await _try_cancel_active_task("chat1", "m1")


# ── doc_section_editor_node ───────────────────────────────────────────────────


def _make_doc_artifact(sections=None):
    from app.schemas.artifacts import DocArtifact, DocSection

    if sections is None:
        sections = [
            DocSection(id="s1", title="背景", content_md="原有内容", block_ids=["b1", "b2"]),
            DocSection(id="s2", title="结论", content_md="结论内容", block_ids=[]),
        ]
    return DocArtifact(doc_id="d1", title="测试文档", sections=sections, share_url="https://x")


def _make_mod_intent(scope_identifier="背景", instruction="重写这节"):
    from app.schemas.enums import ModificationType, ScopeType
    from app.schemas.intent import ModificationIntent

    return ModificationIntent(
        target="document",
        scope_type=ScopeType.specific_section,
        scope_identifier=scope_identifier,
        modification_type=ModificationType.rewrite,
        instruction=instruction,
    )


class TestDocSectionEditorNode:
    @pytest.mark.asyncio
    async def test_missing_mod_intent(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"):
            result = await doc_section_editor_node(
                {"message_id": "m1", "mod_intent": None, "doc": _make_doc_artifact()}
            )
        assert result["status"].value == "completed"

    @pytest.mark.asyncio
    async def test_missing_doc(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"):
            result = await doc_section_editor_node(
                {"message_id": "m1", "mod_intent": _make_mod_intent(), "doc": None}
            )
        assert result["status"].value == "completed"

    @pytest.mark.asyncio
    async def test_section_not_found(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"):
            result = await doc_section_editor_node(
                {
                    "message_id": "m1",
                    "mod_intent": _make_mod_intent(scope_identifier="不存在章节"),
                    "doc": _make_doc_artifact(),
                }
            )
        assert result["status"].value == "completed"

    @pytest.mark.asyncio
    async def test_partial_match(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with (
            patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"),
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("app.services.feishu_doc_service.FeishuDocService") as mock_svc_cls,
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
        ):
            mock_llm.return_value = "新内容"
            mock_svc = AsyncMock()
            mock_svc.patch_section = AsyncMock()
            mock_svc_cls.return_value = mock_svc
            result = await doc_section_editor_node(
                {
                    "message_id": "m1",
                    "mod_intent": _make_mod_intent(scope_identifier="背景"),
                    "doc": _make_doc_artifact(),
                }
            )
        assert result["status"].value == "completed"
        assert result["doc"] is not None

    @pytest.mark.asyncio
    async def test_llm_failure(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with (
            patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"),
            patch(
                "app.services.llm_service.LLMService.invoke",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM down"),
            ),
        ):
            result = await doc_section_editor_node(
                {
                    "message_id": "m1",
                    "mod_intent": _make_mod_intent(),
                    "doc": _make_doc_artifact(),
                }
            )
        assert result["status"].value == "completed"

    @pytest.mark.asyncio
    async def test_success_no_block_ids(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node
        from app.schemas.artifacts import DocSection

        doc = _make_doc_artifact(
            sections=[DocSection(id="s1", title="结论", content_md="旧内容", block_ids=[])]
        )

        with (
            patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"),
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
        ):
            mock_llm.return_value = "新结论内容"
            result = await doc_section_editor_node(
                {
                    "message_id": "m1",
                    "mod_intent": _make_mod_intent(scope_identifier="结论"),
                    "doc": doc,
                    "modification_history": [],
                }
            )

        assert result["status"].value == "completed"
        updated_section = result["doc"].sections[0]
        assert updated_section.content_md == "新结论内容"

    @pytest.mark.asyncio
    async def test_success_with_block_ids_calls_patch(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with (
            patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"),
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("app.services.feishu_doc_service.FeishuDocService") as mock_svc_cls,
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
        ):
            mock_llm.return_value = "新背景内容"
            mock_svc = AsyncMock()
            mock_svc.patch_section = AsyncMock()
            mock_svc_cls.return_value = mock_svc
            result = await doc_section_editor_node(
                {
                    "message_id": "m1",
                    "mod_intent": _make_mod_intent(scope_identifier="背景"),
                    "doc": _make_doc_artifact(),
                    "modification_history": [],
                }
            )

        mock_svc.patch_section.assert_called_once()
        assert result["status"].value == "completed"

    @pytest.mark.asyncio
    async def test_patch_exception_does_not_fail_node(self) -> None:
        from app.graph.nodes.doc_section_editor import doc_section_editor_node

        with (
            patch("app.graph.nodes.doc_section_editor.ProgressBroadcaster"),
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("app.services.feishu_doc_service.FeishuDocService") as mock_svc_cls,
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
        ):
            mock_llm.return_value = "内容"
            mock_svc = AsyncMock()
            mock_svc.patch_section = AsyncMock(side_effect=Exception("patch failed"))
            mock_svc_cls.return_value = mock_svc
            result = await doc_section_editor_node(
                {
                    "message_id": "m1",
                    "mod_intent": _make_mod_intent(scope_identifier="背景"),
                    "doc": _make_doc_artifact(),
                }
            )

        assert result["status"].value == "completed"


# ── ppt_slide_editor_node — chart extract path ────────────────────────────────


def _make_ppt_state_for_editor(instruction: str = "修改图表数据"):
    from app.schemas.artifacts import ChartSchema, ChartSeries, PPTArtifact, SlideSchema
    from app.schemas.enums import SlideLayout
    from app.schemas.intent import ModificationIntent

    slide = SlideSchema(
        page_index=0,
        layout=SlideLayout.title_content,
        title="内容页",
        bullets=["要点1", "要点2"],
        chart=ChartSchema(
            chart_type="bar",
            title="示例图",
            categories=["A", "B"],
            series=[ChartSeries(name="数据", values=[10, 20])],
        ),
    )
    ppt = PPTArtifact(
        ppt_id="ppt1",
        title="测试PPT",
        slides=[slide],
        share_url="https://feishu.example.com/ppt1",
    )
    mod_intent = ModificationIntent(
        target="presentation",
        scope_type="specific_slide",
        scope_identifier="第1页",
        modification_type="rewrite",
        instruction=instruction,
    )
    return {
        "message_id": "m1",
        "chat_id": "c1",
        "ppt": ppt,
        "mod_intent": mod_intent,
        "completed_slide_ids": [],
    }


class TestPptSlideEditorChartExtract:
    @pytest.mark.asyncio
    async def test_chart_extract_no_data_preserves_existing(self) -> None:
        from app.graph.nodes.ppt_slide_editor import ppt_slide_editor_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("app.services.ppt_service.PPTService") as mock_ppt_svc_cls,
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
            patch("app.services.progress_broadcaster.ProgressBroadcaster"),
            patch("redis.asyncio.from_url", return_value=mock_r),
        ):
            text_response = json.dumps(
                {"heading": "内容页", "bullets": ["要点1", "要点2"], "speaker_notes": ""}
            )
            chart_response = json.dumps(
                {"chart_type": "bar", "title": "", "categories": [], "series": []}
            )
            mock_llm.side_effect = [text_response, chart_response]

            mock_ppt_svc = AsyncMock()
            from app.schemas.artifacts import PPTArtifact

            mock_ppt_svc.create_from_outline = AsyncMock(
                return_value=PPTArtifact(
                    ppt_id="ppt2",
                    title="PPT",
                    slides=[],
                    share_url="https://example.com/ppt2",
                )
            )
            mock_ppt_svc_cls.return_value = mock_ppt_svc

            state = _make_ppt_state_for_editor("在图表中添加新数据")
            result = await ppt_slide_editor_node(state)

        assert "ppt" in result

    @pytest.mark.asyncio
    async def test_chart_extract_with_data_replaces_chart(self) -> None:
        from app.graph.nodes.ppt_slide_editor import ppt_slide_editor_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("app.services.ppt_service.PPTService") as mock_ppt_svc_cls,
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
            patch("app.services.progress_broadcaster.ProgressBroadcaster"),
            patch("redis.asyncio.from_url", return_value=mock_r),
        ):
            text_response = json.dumps(
                {"heading": "新标题", "bullets": ["新要点"], "speaker_notes": ""}
            )
            chart_response = json.dumps(
                {
                    "chart_type": "line",
                    "title": "新图表",
                    "categories": ["Q1", "Q2"],
                    "series": [{"name": "收入", "values": [100, 200]}],
                }
            )
            mock_llm.side_effect = [text_response, chart_response]

            mock_ppt_svc = AsyncMock()
            from app.schemas.artifacts import PPTArtifact

            mock_ppt_svc.create_from_outline = AsyncMock(
                return_value=PPTArtifact(
                    ppt_id="ppt2",
                    title="PPT",
                    slides=[],
                    share_url="https://example.com/ppt2",
                )
            )
            mock_ppt_svc_cls.return_value = mock_ppt_svc

            state = _make_ppt_state_for_editor("将折线图更新为季度数据")
            result = await ppt_slide_editor_node(state)

        assert "ppt" in result

    @pytest.mark.asyncio
    async def test_reposition_skips_llm_text_and_preserves_chart(self) -> None:
        from app.graph.nodes.ppt_slide_editor import ppt_slide_editor_node

        mock_r = AsyncMock()
        mock_r.setex = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.llm_service.LLMService.invoke", new_callable=AsyncMock) as mock_llm,
            patch("app.services.ppt_service.PPTService") as mock_ppt_svc_cls,
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
            patch("app.services.progress_broadcaster.ProgressBroadcaster"),
            patch("redis.asyncio.from_url", return_value=mock_r),
        ):
            mock_ppt_svc = AsyncMock()
            from app.schemas.artifacts import PPTArtifact

            mock_ppt_svc.create_from_outline = AsyncMock(
                return_value=PPTArtifact(
                    ppt_id="ppt2",
                    title="PPT",
                    slides=[],
                    share_url="https://example.com/ppt2",
                )
            )
            mock_ppt_svc_cls.return_value = mock_ppt_svc

            state = _make_ppt_state_for_editor("将折线图移动至无重叠区域")
            result = await ppt_slide_editor_node(state)

        mock_llm.assert_not_called()
        assert "ppt" in result
