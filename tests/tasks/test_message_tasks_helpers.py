"""Coverage tests for message_tasks helper functions."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# _parse_message_content
# ---------------------------------------------------------------------------


class TestParseMessageContent:
    def test_none_content_returns_empty(self) -> None:
        from app.tasks.message_tasks import _parse_message_content

        assert _parse_message_content(None, "text") == ""

    def test_text_message(self) -> None:
        import json

        from app.tasks.message_tasks import _parse_message_content

        content = json.dumps({"text": "hello"})
        assert _parse_message_content(content, "text") == "hello"

    def test_audio_message(self) -> None:
        import json

        from app.tasks.message_tasks import _parse_message_content

        content = json.dumps({"file_key": "fk123"})
        assert _parse_message_content(content, "audio") == "fk123"

    def test_invalid_json_returns_empty(self) -> None:
        from app.tasks.message_tasks import _parse_message_content

        assert _parse_message_content("not json", "text") == ""

    def test_unknown_type_returns_empty(self) -> None:
        import json

        from app.tasks.message_tasks import _parse_message_content

        content = json.dumps({"text": "hello"})
        assert _parse_message_content(content, "image") == ""


# ---------------------------------------------------------------------------
# _clear_active_task (sync)
# ---------------------------------------------------------------------------


class TestClearActiveTask:
    def test_no_chat_id_returns_early(self) -> None:
        from app.tasks.message_tasks import _clear_active_task

        _clear_active_task("", "t1")  # no exception

    def test_no_thread_id_returns_early(self) -> None:
        from app.tasks.message_tasks import _clear_active_task

        _clear_active_task("c1", "")  # no exception

    def test_clears_matching_key(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.tasks.message_tasks import _clear_active_task

        mock_r = MagicMock()
        mock_r.get = MagicMock(return_value=b"t1")
        mock_r.delete = MagicMock()

        with patch("redis.from_url", return_value=mock_r):
            _clear_active_task("c1", "t1")
        mock_r.delete.assert_called_once()

    def test_does_not_clear_different_thread(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.tasks.message_tasks import _clear_active_task

        mock_r = MagicMock()
        mock_r.get = MagicMock(return_value=b"other_thread")
        mock_r.delete = MagicMock()

        with patch("redis.from_url", return_value=mock_r):
            _clear_active_task("c1", "t1")
        mock_r.delete.assert_not_called()

    def test_redis_exception_does_not_raise(self) -> None:
        from unittest.mock import patch

        from app.tasks.message_tasks import _clear_active_task

        with patch("redis.from_url", side_effect=RuntimeError("redis unavailable")):
            _clear_active_task("c1", "t1")  # no exception


# ---------------------------------------------------------------------------
# _send_timeout_card_async
# ---------------------------------------------------------------------------


class TestSendTimeoutCardAsync:
    @pytest.mark.asyncio
    async def test_sends_card(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _send_timeout_card_async

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock()
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _send_timeout_card_async("msg1")
        mock_adapter.reply_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _send_timeout_card_async

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock(side_effect=RuntimeError("network"))
        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            await _send_timeout_card_async("msg1")  # no exception


# ---------------------------------------------------------------------------
# _resume_graph_async
# ---------------------------------------------------------------------------


class TestResumeGraphAsync:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _resume_graph_async

        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.setex = AsyncMock()

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks._clear_active_task"),
        ):
            result = await _resume_graph_async("t1", "c1")
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_graph_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _resume_graph_async

        graph = AsyncMock()
        graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph crashed"))

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.setex = AsyncMock()

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks._clear_active_task"),
        ):
            result = await _resume_graph_async("t1", "c1")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_no_chat_id_skips_redis(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _resume_graph_async

        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.message_tasks._clear_active_task"),
        ):
            result = await _resume_graph_async("t1", "")
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# _handle_control_intent
# ---------------------------------------------------------------------------


class TestHandleControlIntent:
    def _make_msg(self, chat_id: str = "c1") -> object:
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.chat_id = chat_id
        return msg

    @pytest.mark.asyncio
    async def test_redis_failure_no_thread_id(self) -> None:
        from unittest.mock import patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = object()
        msg = self._make_msg()
        with patch("redis.asyncio.from_url", side_effect=RuntimeError("redis down")):
            result = await _handle_control_intent(msg, "pause", graph)
        assert result["status"] == "no_active_task"

    @pytest.mark.asyncio
    async def test_pause_updates_state(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock()

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        msg = self._make_msg()
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _handle_control_intent(msg, "pause", graph)
        assert result["status"] == "pause_requested"
        graph.aupdate_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resume_dispatches(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock()

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        mock_task = MagicMock()
        mock_task.delay = MagicMock()

        msg = self._make_msg()
        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_control_intent(msg, "resume", graph)
        assert result["status"] == "resumed"

    @pytest.mark.asyncio
    async def test_cancel_dispatches(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock()

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        mock_task = MagicMock()
        mock_task.delay = MagicMock()

        msg = self._make_msg()
        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_control_intent(msg, "cancel", graph)
        assert result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_unknown_control_returns_unknown(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        msg = self._make_msg()
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _handle_control_intent(msg, "teleport", graph)
        assert result["status"] == "unknown_control"


# ---------------------------------------------------------------------------
# _handle_lego_command
# ---------------------------------------------------------------------------


class TestHandleLegoCommand:
    @pytest.mark.asyncio
    async def test_sends_lego_card(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_lego_command

        msg = MagicMock()
        msg.message_id = "msg1"
        msg.chat_id = "c1"

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock()

        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            result = await _handle_lego_command(msg)
        assert result["status"] == "lego_card_sent"
        mock_adapter.reply_card.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_lego_command

        msg = MagicMock()
        msg.message_id = "msg1"
        msg.chat_id = "c1"

        mock_adapter = AsyncMock()
        mock_adapter.reply_card = AsyncMock(side_effect=RuntimeError("network"))

        with patch("app.integrations.feishu.adapter.FeishuAdapter", return_value=mock_adapter):
            result = await _handle_lego_command(msg)
        assert result["status"] == "lego_card_sent"


# ---------------------------------------------------------------------------
# _handle_stage1
# ---------------------------------------------------------------------------


def _make_msg(
    text: str = "你好",
    chat_id: str = "c1",
    message_id: str = "m1",
    message_type: str = "text",
    file_key: str = "",
) -> object:
    from unittest.mock import MagicMock

    msg = MagicMock()
    msg.text = text
    msg.chat_id = chat_id
    msg.message_id = message_id
    msg.message_type = message_type
    msg.file_key = file_key
    msg.sender_user_id = "u1"
    msg.event_id = "ev1"
    return msg


class TestHandleStage1:
    @pytest.mark.asyncio
    async def test_text_message_success(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg()
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService"),
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.reply_text = AsyncMock()
            mock_fa_cls.return_value = mock_fa
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(return_value="Hi!")
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        assert result["status"] == "completed"
        mock_fa.reply_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_text_message_no_message_id_uses_send_text(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg(message_id="")
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService"),
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.send_text = AsyncMock()
            mock_fa_cls.return_value = mock_fa
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(return_value="Hi!")
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        assert result["status"] == "completed"
        mock_fa.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_text_returns_received(self) -> None:
        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg(text="   ")
        result = await _handle_stage1(msg)
        assert result["status"] == "received"

    @pytest.mark.asyncio
    async def test_demo_intent_dispatches(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg(text="生成演示文档")
        mock_demo_task = MagicMock()
        mock_demo_task.delay = MagicMock()
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter"),
            patch("app.services.asr_service.ASRService"),
            patch("app.services.echo_responder.EchoResponder"),
            patch("app.services.intent_router.classify", return_value="generate_demo"),
            patch("app.tasks.demo_tasks.handle_demo_request_task", mock_demo_task),
        ):
            result = await _handle_stage1(msg)
        assert result["status"] == "dispatched"
        mock_demo_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_responder_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg()
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService"),
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.reply_text = AsyncMock()
            mock_fa_cls.return_value = mock_fa
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(side_effect=RuntimeError("LLM down"))
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_responder_exception_feishu_error_still_returns_error(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg()
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService"),
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.reply_text = AsyncMock(side_effect=RuntimeError("feishu down"))
            mock_fa_cls.return_value = mock_fa
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(side_effect=RuntimeError("LLM down"))
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_audio_message_transcription(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg(text="", message_type="audio", file_key="fk1")
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService") as mock_asr_cls,
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.reply_text = AsyncMock()
            mock_fa_cls.return_value = mock_fa
            mock_asr = AsyncMock()
            mock_asr.transcribe_voice_message = AsyncMock(return_value="语音转文字")
            mock_asr_cls.return_value = mock_asr
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(return_value="response")
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_responder_exception_no_message_id_feishu_error(self) -> None:
        """Covers the no-message_id error reply branch (line 460)."""
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg(message_id="")
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService"),
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.send_text = AsyncMock(side_effect=RuntimeError("feishu down"))
            mock_fa_cls.return_value = mock_fa
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(side_effect=RuntimeError("LLM down"))
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_audio_empty_transcription_fallback(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_stage1

        msg = _make_msg(text="", message_type="audio", file_key="fk1")
        with (
            patch("app.integrations.feishu.adapter.FeishuAdapter") as mock_fa_cls,
            patch("app.services.asr_service.ASRService") as mock_asr_cls,
            patch("app.services.echo_responder.EchoResponder") as mock_responder_cls,
            patch("app.services.intent_router.classify", return_value="echo"),
        ):
            mock_fa = AsyncMock()
            mock_fa.reply_text = AsyncMock()
            mock_fa_cls.return_value = mock_fa
            mock_asr = AsyncMock()
            mock_asr.transcribe_voice_message = AsyncMock(return_value="")
            mock_asr_cls.return_value = mock_asr
            mock_responder = AsyncMock()
            mock_responder.respond = AsyncMock(return_value="response")
            mock_responder_cls.return_value = mock_responder
            result = await _handle_stage1(msg)
        # [语音内容无法识别] is non-empty so it proceeds
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# _handle_lego_text
# ---------------------------------------------------------------------------


class TestHandleLegoText:
    def _make_msg(
        self,
        text: str = "帮我做PPT",
        chat_id: str = "c1",
        message_id: str = "m1",
    ) -> object:
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.text = text
        msg.chat_id = chat_id
        msg.message_id = message_id
        msg.sender_user_id = "u1"
        return msg

    @pytest.mark.asyncio
    async def test_success_with_C_and_D_scenarios(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_lego_text

        msg = self._make_msg()
        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.db.engine.get_session", return_value=mock_session_ctx),
            patch("app.repositories.task_repo.create_task", new_callable=AsyncMock),
        ):
            result = await _handle_lego_text(msg, ["C", "D"])
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_success_with_only_C(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_lego_text

        msg = self._make_msg()
        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.db.engine.get_session", return_value=mock_session_ctx),
            patch("app.repositories.task_repo.create_task", new_callable=AsyncMock),
        ):
            result = await _handle_lego_text(msg, ["C"])
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_graph_exception_returns_error(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_lego_text

        msg = self._make_msg()
        graph = AsyncMock()
        graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph crashed"))

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.db.engine.get_session", return_value=mock_session_ctx),
            patch("app.repositories.task_repo.create_task", new_callable=AsyncMock),
        ):
            result = await _handle_lego_text(msg, ["D"])
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_db_exception_does_not_abort(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_lego_text

        msg = self._make_msg()
        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.db.engine.get_session", side_effect=RuntimeError("db down")),
        ):
            result = await _handle_lego_text(msg, ["C"])
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_text_uses_default_goal(self) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_lego_text

        msg = self._make_msg(text="")
        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.db.engine.get_session", return_value=mock_session_ctx),
            patch("app.repositories.task_repo.create_task", new_callable=AsyncMock),
        ):
            result = await _handle_lego_text(msg, [])
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# _handle_message_async - unsupported message type
# ---------------------------------------------------------------------------


class TestHandleMessageAsync:
    @pytest.mark.asyncio
    async def test_unsupported_message_type_returns_received(self) -> None:
        from unittest.mock import MagicMock, patch

        from app.tasks.message_tasks import _handle_message_async

        mock_settings = MagicMock()
        mock_settings.FORGE_USE_GRAPH = False

        mock_msg = MagicMock()
        mock_msg.message_type = "unsupported"
        mock_msg.message_id = "m1"

        with (
            patch("app.services.message_router.parse_message", return_value=mock_msg),
            patch("app.config.get_settings", return_value=mock_settings),
        ):
            result = await _handle_message_async({})
        assert result["status"] == "received"

    @pytest.mark.asyncio
    async def test_stage1_path_dispatched(self) -> None:
        """Line 51: FORGE_USE_GRAPH=False → calls _handle_stage1."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_message_async

        mock_settings = MagicMock()
        mock_settings.FORGE_USE_GRAPH = False

        mock_msg = MagicMock()
        mock_msg.message_type = "text"
        mock_msg.message_id = "m1"
        mock_msg.text = "hello"
        mock_msg.chat_id = "c1"

        with (
            patch("app.services.message_router.parse_message", return_value=mock_msg),
            patch("app.config.get_settings", return_value=mock_settings),
            patch(
                "app.tasks.message_tasks._handle_stage1",
                new_callable=AsyncMock,
                return_value={"status": "completed", "message_id": "m1"},
            ),
        ):
            result = await _handle_message_async({})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_graph_path_lego_command_dispatched(self) -> None:
        """Line 49: FORGE_USE_GRAPH=True → calls _handle_via_graph → /lego path."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_message_async

        mock_settings = MagicMock()
        mock_settings.FORGE_USE_GRAPH = True

        mock_msg = MagicMock()
        mock_msg.message_type = "text"
        mock_msg.message_id = "m1"
        mock_msg.chat_id = "c1"
        mock_msg.text = "/lego"

        with (
            patch("app.services.message_router.parse_message", return_value=mock_msg),
            patch("app.config.get_settings", return_value=mock_settings),
            patch(
                "app.tasks.message_tasks._handle_lego_command",
                new_callable=AsyncMock,
                return_value={"status": "lego_card_sent", "message_id": "m1"},
            ),
        ):
            result = await _handle_message_async({})
        assert result["status"] == "lego_card_sent"


# ---------------------------------------------------------------------------
# _handle_control_intent — exception paths
# ---------------------------------------------------------------------------


class TestHandleControlIntentExceptions:
    def _make_msg(self, chat_id: str = "c1") -> object:
        from unittest.mock import MagicMock

        msg = MagicMock()
        msg.chat_id = chat_id
        return msg

    @pytest.mark.asyncio
    async def test_pause_update_state_exception_still_returns(self) -> None:
        """Line 386: exception in graph.aupdate_state for pause."""
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock(side_effect=RuntimeError("state update failed"))

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        msg = self._make_msg()
        with patch("redis.asyncio.from_url", return_value=mock_r):
            result = await _handle_control_intent(msg, "pause", graph)
        assert result["status"] == "pause_requested"

    @pytest.mark.asyncio
    async def test_resume_exception_still_returns(self) -> None:
        """Line 396: exception in update_state or delay for resume."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock(side_effect=RuntimeError("state failed"))

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        mock_task = MagicMock()
        mock_task.delay = MagicMock()

        msg = self._make_msg()
        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_control_intent(msg, "resume", graph)
        assert result["status"] == "resumed"

    @pytest.mark.asyncio
    async def test_cancel_exception_still_returns(self) -> None:
        """Line 412: exception in update_state for cancel."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_control_intent

        graph = AsyncMock()
        graph.aupdate_state = AsyncMock(side_effect=RuntimeError("state failed"))

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=b"thread1")

        mock_task = MagicMock()
        mock_task.delay = MagicMock()

        msg = self._make_msg()
        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks.resume_graph_task", mock_task),
        ):
            result = await _handle_control_intent(msg, "cancel", graph)
        assert result["status"] == "cancelled"


# ---------------------------------------------------------------------------
# _resume_graph_async — Redis exception path
# ---------------------------------------------------------------------------


class TestResumeGraphAsyncRedisException:
    @pytest.mark.asyncio
    async def test_redis_register_exception_still_completes(self) -> None:
        """Line 327: exception in Redis setex still completes graph run."""
        from unittest.mock import AsyncMock, patch

        from app.tasks.message_tasks import _resume_graph_async

        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})

        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.setex = AsyncMock(side_effect=RuntimeError("redis unavailable"))

        with (
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.tasks.message_tasks._clear_active_task"),
        ):
            result = await _resume_graph_async("t1", "c1")
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# _handle_via_graph — control intent path, no active task (lines 67-86)
# ---------------------------------------------------------------------------


class TestHandleViaGraphControlPath:
    @pytest.mark.asyncio
    async def test_control_intent_no_active_task_falls_through(self) -> None:
        """Lines 67-86: control word detected but no active task → falls through to graph run."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.tasks.message_tasks import _handle_via_graph

        mock_msg = MagicMock()
        mock_msg.text = "取消"
        mock_msg.chat_id = "c1"
        mock_msg.message_id = "m1"

        # Redis mock: get() returns None (no active task), set() returns True (dedup passes)
        mock_r = AsyncMock()
        mock_r.__aenter__ = AsyncMock(return_value=mock_r)
        mock_r.__aexit__ = AsyncMock(return_value=None)
        mock_r.get = AsyncMock(return_value=None)
        mock_r.set = AsyncMock(return_value=True)

        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://localhost:6379"

        graph = AsyncMock()
        graph.ainvoke = AsyncMock(return_value={"status": "completed"})
        graph.aget_state = AsyncMock(return_value=None)

        with (
            patch("redis.asyncio.from_url", return_value=mock_r),
            patch("app.config.get_settings", return_value=mock_settings),
            patch(
                "app.graph.nodes.checkpoint_control.detect_control_intent",
                return_value="cancel",
            ),
            patch("app.graph.get_or_init_graph", new_callable=AsyncMock, return_value=graph),
            patch("app.tasks.message_tasks._handle_lego_text", new_callable=AsyncMock),
            patch("app.tasks.message_tasks._clear_active_task"),
        ):
            result = await _handle_via_graph(mock_msg, {})
        assert result is not None
