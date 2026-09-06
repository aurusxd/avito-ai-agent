import pytest
from pydantic import ValidationError

from app.clients.ai.base import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIUnavailableError,
    AIVariationRequest,
    AIVariationResponse,
)
from app.clients.ai.chain import FallbackAIClient
from app.clients.ai.fake import FakeAIClient

REQUEST = AIVariationRequest(
    template_text="Здравствуйте, {name}!",
    seller_name="Артём",
    product="баня",
    category="Бани",
)


class StubClient:
    def __init__(self, provider: str, answer: str | None = None, error: Exception | None = None):
        self.provider = provider
        self.answer = answer
        self.error = error
        self.calls = 0

    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIVariationResponse(unique_text=self.answer or "ok")

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIAnalysisResponse(sentiment="neutral", confidence=0.5)


async def test_primary_answer_keeps_the_fallback_untouched() -> None:
    primary = StubClient("deepseek", answer="от deepseek")
    fallback = StubClient("openai", answer="от openai")
    chain = FallbackAIClient(primary, fallback)

    response = await chain.rewrite(REQUEST)

    assert response.unique_text == "от deepseek"
    assert fallback.calls == 0
    assert chain.last_provider == "deepseek"


async def test_unavailable_primary_switches_to_the_fallback() -> None:
    primary = StubClient("deepseek", error=AIUnavailableError("down", "deepseek", 503))
    fallback = StubClient("openai", answer="от openai")
    chain = FallbackAIClient(primary, fallback)

    response = await chain.rewrite(REQUEST)

    assert response.unique_text == "от openai"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert chain.last_provider == "openai"


async def test_both_providers_down_propagates_the_fallback_error() -> None:
    primary = StubClient("deepseek", error=AIUnavailableError("down", "deepseek", 503))
    fallback = StubClient("openai", error=AIUnavailableError("also down", "openai", 500))
    chain = FallbackAIClient(primary, fallback)

    with pytest.raises(AIUnavailableError) as error:
        await chain.rewrite(REQUEST)

    assert error.value.provider == "openai"


async def test_unexpected_primary_error_is_not_swallowed() -> None:
    primary = StubClient("deepseek", error=ValueError("bug in our code"))
    fallback = StubClient("openai", answer="от openai")
    chain = FallbackAIClient(primary, fallback)

    with pytest.raises(ValueError):
        await chain.rewrite(REQUEST)

    assert fallback.calls == 0


async def test_chain_validates_garbage_before_calling_anyone() -> None:
    primary = StubClient("deepseek", answer="ok")
    fallback = StubClient("openai", answer="ok")
    chain = FallbackAIClient(primary, fallback)

    with pytest.raises(ValidationError):
        await chain.rewrite({"template_text": ""})  # type: ignore[arg-type]

    assert primary.calls == 0
    assert fallback.calls == 0


async def test_analysis_also_falls_back() -> None:
    primary = StubClient("deepseek", error=AIUnavailableError("down", "deepseek"))
    chain = FallbackAIClient(primary, FakeAIClient())

    response = await chain.analyze_reply(AIAnalysisRequest(reply_text="Да, интересно"))

    assert response.sentiment == "interested"
    assert chain.last_provider == "fake"
