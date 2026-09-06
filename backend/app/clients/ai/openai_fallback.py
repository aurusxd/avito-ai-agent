import httpx

from app.clients.ai.openai_compatible import OpenAICompatibleClient
from app.config import Settings, get_settings


class OpenAIFallbackClient(OpenAICompatibleClient):
    provider = "openai"

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved = settings or get_settings()
        super().__init__(
            api_key=resolved.openai_api_key,
            base_url=resolved.openai_base_url,
            model=resolved.openai_model,
            settings=resolved,
            transport=transport,
        )
