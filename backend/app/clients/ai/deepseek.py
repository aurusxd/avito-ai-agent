import httpx

from app.clients.ai.openai_compatible import OpenAICompatibleClient
from app.config import Settings, get_settings


class DeepSeekClient(OpenAICompatibleClient):
    provider = "deepseek"

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved = settings or get_settings()
        super().__init__(
            api_key=resolved.deepseek_api_key,
            base_url=resolved.deepseek_base_url,
            model=resolved.deepseek_model,
            settings=resolved,
            transport=transport,
        )
