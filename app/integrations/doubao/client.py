from typing import Literal

from langchain_openai import ChatOpenAI

from app.config import get_settings


def get_llm(tier: Literal["pro", "lite"] = "pro") -> ChatOpenAI:
    """Factory for Doubao LLM client using the Ark OpenAI-compatible API.

    Doubao uses endpoint IDs (ep-xxx) instead of model names.
    base_url must NOT have a trailing /v1 — the SDK adds it automatically.
    """
    settings = get_settings()
    model = settings.DOUBAO_MODEL_PRO if tier == "pro" else settings.DOUBAO_MODEL_LITE
    return ChatOpenAI(
        model=model,
        api_key=settings.DOUBAO_API_KEY,
        base_url=settings.DOUBAO_BASE_URL,
        temperature=0.3,
        max_tokens=4096,
    )
