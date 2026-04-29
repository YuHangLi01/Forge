class ForgeError(Exception):
    """Base exception for all Forge domain errors."""

    def __init__(self, message: str, code: int = -1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class IntentParseError(ForgeError):
    """LLM returned an intent that could not be parsed into IntentSchema."""


class FeishuAPIError(ForgeError):
    """Feishu OpenAPI returned a non-zero code or unexpected response."""

    def __init__(self, message: str, feishu_code: int = 0) -> None:
        super().__init__(message)
        self.feishu_code = feishu_code


class FeishuRateLimitError(FeishuAPIError):
    """Feishu API rate limit exceeded (code 99991663)."""


class ASRError(ForgeError):
    """Volcano Engine ASR transcription failed."""


class LLMError(ForgeError):
    """Doubao / LLM call failed after retries."""


class CheckpointError(ForgeError):
    """LangGraph checkpoint save/load failed."""
