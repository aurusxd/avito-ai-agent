from loguru import logger

from app.clients.ai.base import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIClient,
    AIUnavailableError,
    AIVariationRequest,
    AIVariationResponse,
)


class FallbackAIClient:
    provider = "chain"

    def __init__(self, primary: AIClient, fallback: AIClient) -> None:
        self.primary = primary
        self.fallback = fallback
        self.last_provider: str | None = None

    def _name(self, client: AIClient) -> str:
        return getattr(client, "provider", type(client).__name__)

    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse:
        validated = AIVariationRequest.model_validate(request)
        try:
            response = await self.primary.rewrite(validated)
        except AIUnavailableError as error:
            logger.warning(
                "primary ai provider {provider} unavailable, falling back: {reason}",
                provider=self._name(self.primary),
                reason=str(error),
            )
            response = await self.fallback.rewrite(validated)
            self.last_provider = self._name(self.fallback)
            return response

        self.last_provider = self._name(self.primary)
        return response

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        validated = AIAnalysisRequest.model_validate(request)
        try:
            response = await self.primary.analyze_reply(validated)
        except AIUnavailableError as error:
            logger.warning(
                "primary ai provider {provider} unavailable, falling back: {reason}",
                provider=self._name(self.primary),
                reason=str(error),
            )
            response = await self.fallback.analyze_reply(validated)
            self.last_provider = self._name(self.fallback)
            return response

        self.last_provider = self._name(self.primary)
        return response
