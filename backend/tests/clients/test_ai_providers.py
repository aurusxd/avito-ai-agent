import httpx
import pytest
from pydantic import ValidationError

from app.clients.ai.base import AIAnalysisRequest, AIUnavailableError, AIVariationRequest
from app.clients.ai.deepseek import DeepSeekClient
from app.clients.ai.openai_fallback import OpenAIFallbackClient
from app.config import Settings

API_KEY = "sk-secret-value"

REQUEST = AIVariationRequest(
    template_text="Здравствуйте, {name}! Ваш «{product}» актуален?",
    seller_name="Артём",
    product="баня-бочка",
    category="Бани",
)


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "deepseek_api_key": API_KEY,
        "openai_api_key": API_KEY,
        "ai_max_retries": 1,
        "ai_retry_backoff_seconds": 0.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def completion(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


async def test_deepseek_sends_expected_request_and_parses_content() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completion("Артём, баня ещё в работе?"))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    response = await client.rewrite(REQUEST)

    assert response.unique_text == "Артём, баня ещё в работе?"
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "https://api.deepseek.com/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"

    import json

    body = json.loads(request.content)
    assert body["model"] == "deepseek-chat"
    assert body["stream"] is False
    assert [message["role"] for message in body["messages"]] == ["system", "user"]
    assert "баня-бочка" in body["messages"][1]["content"]
    assert "Артём" in body["messages"][1]["content"]


async def test_openai_fallback_uses_its_own_base_url_and_model() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completion("Здравствуйте, Артём!"))

    client = OpenAIFallbackClient(settings(), transport=httpx.MockTransport(handler))

    await client.rewrite(REQUEST)

    import json

    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"
    assert json.loads(seen[0].content)["model"] == "gpt-4o-mini"


async def test_missing_api_key_fails_without_a_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=completion("нет"))

    client = DeepSeekClient(settings(deepseek_api_key=""), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError) as error:
        await client.rewrite(REQUEST)

    assert calls == 0
    assert error.value.provider == "deepseek"


async def test_retryable_status_is_retried_then_reported() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="upstream down")

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError) as error:
        await client.rewrite(REQUEST)

    assert calls == 2
    assert error.value.status_code == 503


async def test_retry_recovers_on_the_second_attempt() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json=completion("Артём, актуально?"))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    response = await client.rewrite(REQUEST)

    assert calls == 2
    assert response.unique_text == "Артём, актуально?"


async def test_non_retryable_status_fails_immediately() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, text="bad key")

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError) as error:
        await client.rewrite(REQUEST)

    assert calls == 1
    assert error.value.status_code == 401


async def test_transport_error_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError) as error:
        await client.rewrite(REQUEST)

    assert "ConnectTimeout" in str(error.value)


async def test_unreadable_payload_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError):
        await client.rewrite(REQUEST)


async def test_empty_completion_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion("   "))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError):
        await client.rewrite(REQUEST)


async def test_api_key_never_leaks_into_the_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError) as error:
        await client.rewrite(REQUEST)

    assert API_KEY not in str(error.value)


async def test_garbage_request_is_rejected_before_any_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=completion("нет"))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(ValidationError):
        await client.rewrite({"template_text": "", "seller_name": 1})  # type: ignore[arg-type]

    assert calls == 0


async def test_analyze_reply_parses_the_json_answer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json=completion('{"sentiment": "interested", "confidence": 0.83}')
        )

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    response = await client.analyze_reply(AIAnalysisRequest(reply_text="Да, расскажите"))

    assert response.sentiment == "interested"
    assert response.confidence == 0.83

    import json

    body = json.loads(seen[0].content)
    assert "Да, расскажите" in body["messages"][1]["content"]


async def test_analyze_reply_accepts_a_fenced_json_answer() -> None:
    fenced = """Готово:
```json
{"sentiment": "negative", "confidence": 0.9}
```"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(fenced))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    response = await client.analyze_reply(AIAnalysisRequest(reply_text="Не пишите"))

    assert response.sentiment == "negative"
    assert response.confidence == 0.9


async def test_unclassifiable_answer_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion("продавец вроде бы заинтересован"))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError):
        await client.analyze_reply(AIAnalysisRequest(reply_text="Да"))


async def test_analyze_reply_rejects_garbage_before_any_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=completion("{}"))

    client = DeepSeekClient(settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(ValidationError):
        await client.analyze_reply({"reply_text": ""})  # type: ignore[arg-type]

    assert calls == 0
