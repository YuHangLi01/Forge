import asyncio
from collections.abc import AsyncIterator
from typing import Literal, TypeVar

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.integrations.doubao.client import get_llm

logger = structlog.get_logger(__name__)

T = TypeVar("T")

_SYSTEM_PROMPT = "你是 Forge，飞书智能办公助手。请简洁、专业地回答用户问题。"

_RATE_LIMIT_MAX_RETRIES = 4
_RATE_LIMIT_BASE_DELAY = 5.0  # seconds; doubles each retry (5s → 10s → 20s → 40s)


class LLMService:
    async def invoke(self, prompt: str, tier: Literal["pro", "lite"] = "pro") -> str:
        llm = get_llm(tier)
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]

        delay = _RATE_LIMIT_BASE_DELAY
        for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
            try:
                response = await llm.ainvoke(messages)
                break
            except Exception as exc:
                # Retry on 429 rate-limit errors; re-raise anything else immediately.
                err_str = str(exc)
                is_rate_limit = "429" in err_str or "RateLimitExceeded" in err_str
                if not is_rate_limit or attempt == _RATE_LIMIT_MAX_RETRIES:
                    raise
                logger.warning(
                    "llm_rate_limited_retrying",
                    tier=tier,
                    attempt=attempt + 1,
                    retry_after_s=delay,
                )
                await asyncio.sleep(delay)
                delay *= 2

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
            result: T = schema.model_validate(data)
        else:
            result = schema(**data)

        logger.info("llm_structured", tier=tier, schema=schema.__name__)
        return result

    async def stream(
        self, prompt: str, tier: Literal["pro", "lite"] = "lite"
    ) -> AsyncIterator[str]:
        llm = get_llm(tier)
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        async for chunk in llm.astream(messages):
            yield str(chunk.content)
