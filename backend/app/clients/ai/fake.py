from app.clients.ai.base import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIVariationRequest,
    AIVariationResponse,
)
from app.domain.templates import render_template

INTERESTED_MARKERS = ("да", "интересно", "давайте", "готов", "расскажите", "сколько")
NEGATIVE_MARKERS = ("нет", "не интересно", "не пишите", "спам", "отстаньте")


class FakeAIClient:
    def __init__(self, failure: Exception | None = None, fail_times: int = 0) -> None:
        self.failure = failure
        self.fail_times = fail_times
        self.rewrite_calls: list[AIVariationRequest] = []
        self.analysis_calls: list[AIAnalysisRequest] = []

    def _maybe_fail(self) -> None:
        if self.failure is not None and self.fail_times > 0:
            self.fail_times -= 1
            raise self.failure

    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse:
        validated = AIVariationRequest.model_validate(request)
        self.rewrite_calls.append(validated)
        self._maybe_fail()
        text = render_template(
            validated.template_text,
            name=validated.seller_name,
            product=validated.product,
            category=validated.category,
        )
        return AIVariationResponse(unique_text=text)

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        validated = AIAnalysisRequest.model_validate(request)
        self.analysis_calls.append(validated)
        self._maybe_fail()
        lowered = validated.reply_text.lower()
        if any(marker in lowered for marker in NEGATIVE_MARKERS):
            return AIAnalysisResponse(sentiment="negative", confidence=0.9)
        if any(marker in lowered for marker in INTERESTED_MARKERS):
            return AIAnalysisResponse(sentiment="interested", confidence=0.8)
        return AIAnalysisResponse(sentiment="neutral", confidence=0.5)
