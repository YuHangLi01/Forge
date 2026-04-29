import structlog

from app.services.llm_service import LLMService

logger = structlog.get_logger(__name__)


class EchoResponder:
    def __init__(self) -> None:
        self._llm = LLMService()

    async def respond(self, chat_id: str, message_id: str, user_text: str) -> str:
        prompt = f"你是Forge助手，请简洁回答用户的问题：\n\n{user_text}"
        reply = await self._llm.invoke(prompt)
        logger.info("echo_responded", chat_id=chat_id, message_id=message_id, reply_len=len(reply))
        return reply
