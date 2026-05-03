"""Coverage tests for EchoResponder."""

from __future__ import annotations

import pytest


class TestEchoResponder:
    @pytest.mark.asyncio
    async def test_respond_returns_reply(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.services.echo_responder import EchoResponder

        patch_target = "app.services.llm_service.LLMService.invoke"
        with patch(patch_target, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "你好，我是Forge助手"
            responder = EchoResponder()
            result = await responder.respond("c1", "m1", "你好")

        assert result == "你好，我是Forge助手"
        mock_llm.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respond_passes_user_text_in_prompt(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.services.echo_responder import EchoResponder

        patch_target = "app.services.llm_service.LLMService.invoke"
        with patch(patch_target, new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "回答"
            responder = EchoResponder()
            await responder.respond("c1", "m1", "测试问题")

        prompt_used = mock_llm.call_args[0][0]
        assert "测试问题" in prompt_used
