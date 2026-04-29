from collections.abc import AsyncIterator
from typing import Literal, TypeVar

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.integrations.doubao.client import get_llm

logger = structlog.get_logger(__name__)

T = TypeVar("T")

_SYSTEM_PROMPT = "你是 Forge，飞书智能办公助手。请简洁、专业地回答用户问题。"


class LLMService:
    async def invoke(self, prompt: str, tier: Literal["pro", "lite"] = "pro") -> str:
        llm = get_llm(tier)
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = await llm.ainvoke(messages)
        content = str(response.content)
        usage = getattr(response, "usage_metadata", {})
        logger.info(
            "llm_invoked",
            tier=tier,
            prompt_len=len(prompt),
            response_len=len(content),
            usage=usage,
        )
        return content

    async def structured(
        self,
        prompt: str,
        schema: type[T],
        tier: Literal["pro", "lite"] = "pro",
    ) -> T:
        llm = get_llm(tier)
        structured_llm = llm.with_structured_output(schema)
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        result: T = await structured_llm.ainvoke(messages)  # type: ignore[assignment]
        logger.info("llm_structured", tier=tier, schema=schema.__name__)
        return result

    async def stream(
        self, prompt: str, tier: Literal["pro", "lite"] = "lite"
    ) -> AsyncIterator[str]:
        llm = get_llm(tier)
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        async for chunk in llm.astream(messages):
            yield str(chunk.content)
