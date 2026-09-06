from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from app.clients.ai.base import AIClient


def get_ai_client() -> "AIClient":
    choice = get_settings().ai_client

    if choice == "deepseek":
        from app.clients.ai.deepseek import DeepSeekClient

        return DeepSeekClient()

    if choice == "openai":
        from app.clients.ai.openai_fallback import OpenAIFallbackClient

        return OpenAIFallbackClient()

    if choice == "chain":
        from app.clients.ai.chain import FallbackAIClient
        from app.clients.ai.deepseek import DeepSeekClient
        from app.clients.ai.openai_fallback import OpenAIFallbackClient

        return FallbackAIClient(DeepSeekClient(), OpenAIFallbackClient())

    from app.clients.ai.fake import FakeAIClient

    return FakeAIClient()
