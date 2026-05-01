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
        # Reasoning models return content as a list; extract text part.
        raw = response.content
        content = (
            next((b["text"] for b in raw if isinstance(b, dict) and b.get("type") == "text"), "")
            if isinstance(raw, list)
            else str(raw)
        )
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
        import json
        import re

        from pydantic import BaseModel

        # Reasoning models (doubao-seed-*) don't support function calling.
        # Ask the model to reply with a JSON block; parse it manually.
        json_prompt = (
            f"{prompt}\n\n" "请以 JSON 格式输出，用 ```json ... ``` 包裹，不要输出其他内容。"
        )
        raw_text = await self.invoke(json_prompt, tier=tier)

        # Extract the first ```json ... ``` block, or fall back to the whole response.
        match = re.search(r"```json\s*(.*?)```", raw_text, re.DOTALL)
        json_str = match.group(1).strip() if match else raw_text.strip()

        data = json.loads(json_str)
        if issubclass(schema, BaseModel):
            result: T = schema.model_validate(data)  # type: ignore[assignment]
        else:
            result = schema(**data)  # type: ignore[assignment]

        logger.info("llm_structured", tier=tier, schema=schema.__name__)
        return result

    async def stream(
        self, prompt: str, tier: Literal["pro", "lite"] = "lite"
    ) -> AsyncIterator[str]:
        llm = get_llm(tier)
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        async for chunk in llm.astream(messages):
            yield str(chunk.content)
