import asyncio

import httpx
from loguru import logger

from app.clients.ai.base import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIUnavailableError,
    AIVariationRequest,
    AIVariationResponse,
)
from app.config import Settings, get_settings
from app.domain.replies import parse_sentiment_payload

REWRITE_SYSTEM_PROMPT = (
    "Ты помогаешь переписывать короткие деловые сообщения продавцам на Авито. "
    "Верни ровно одно сообщение на русском языке, без кавычек, без пояснений, "
    "без подписи и без markdown. Сохрани смысл и вопрос исходного текста, "
    "сделай формулировку живой и естественной. Обращайся к продавцу на «вы». "
    "Не выдумывай факты о товаре, цене и сроках. Не используй фигурные скобки. "
    "Держись в пределах двух предложений."
)

ANALYSIS_SYSTEM_PROMPT = (
    "Ты классифицируешь ответы продавцов на Авито на холодное сообщение. "
    "Верни строго один JSON-объект с полями sentiment и confidence, "
    "без markdown, без пояснений и без текста вокруг. "
    "sentiment принимает ровно одно из значений: interested, neutral, negative. "
    "interested — продавец готов обсуждать, спрашивает детали, соглашается. "
    "neutral — ответ без явного интереса и без отказа, например отписка или уточнение. "
    "negative — отказ, просьба не писать, грубость. "
    "confidence — твоя уверенность, дробное число от 0 до 1."
)

RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def build_analysis_prompt(request: AIAnalysisRequest) -> str:
    return f"Ответ продавца:\n{request.reply_text}\n\nКлассифицируй этот ответ."


def build_rewrite_prompt(request: AIVariationRequest) -> str:
    return (
        f"Категория: {request.category}\n"
        f"Товар или услуга продавца: {request.product}\n"
        f"Имя продавца: {request.seller_name}\n\n"
        f"Исходное сообщение:\n{request.template_text}\n\n"
        "Перепиши это сообщение под конкретного получателя."
    )


class OpenAICompatibleClient:
    provider = "openai-compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        settings: Settings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.settings = settings or get_settings()
        self.transport = transport

    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse:
        validated = AIVariationRequest.model_validate(request)
        content = await self._chat(REWRITE_SYSTEM_PROMPT, build_rewrite_prompt(validated))
        if not content.strip():
            raise AIUnavailableError("model returned an empty message", self.provider)
        return AIVariationResponse(unique_text=content)

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        validated = AIAnalysisRequest.model_validate(request)
        content = await self._chat(ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt(validated))

        parsed = parse_sentiment_payload(content)
        if parsed is None:
            raise AIUnavailableError(
                f"{self.provider} returned an unclassifiable answer", self.provider
            )

        sentiment, confidence = parsed
        return AIAnalysisResponse(sentiment=sentiment, confidence=confidence)

    async def _chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise AIUnavailableError(f"{self.provider} api key is not configured", self.provider)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.ai_temperature,
            "max_tokens": self.settings.ai_max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        attempts = self.settings.ai_max_retries + 1
        last_error: AIUnavailableError | None = None

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.settings.ai_timeout_seconds,
            transport=self.transport,
        ) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.post("/chat/completions", json=payload, headers=headers)
                except httpx.HTTPError as error:
                    last_error = AIUnavailableError(
                        f"{self.provider} transport error: {type(error).__name__}", self.provider
                    )
                else:
                    if response.status_code < 400:
                        return self._extract_content(response)
                    last_error = AIUnavailableError(
                        f"{self.provider} returned http {response.status_code}",
                        self.provider,
                        response.status_code,
                    )
                    if response.status_code not in RETRYABLE_STATUS:
                        raise last_error

                logger.warning(
                    "ai call to {provider} failed ({attempt}/{attempts}): {reason}",
                    provider=self.provider,
                    attempt=attempt,
                    attempts=attempts,
                    reason=str(last_error),
                )
                if attempt < attempts:
                    await asyncio.sleep(self.settings.ai_retry_backoff_seconds * attempt)

        raise last_error or AIUnavailableError(f"{self.provider} is unavailable", self.provider)

    def _extract_content(self, response: httpx.Response) -> str:
        try:
            choices = response.json()["choices"]
            return str(choices[0]["message"]["content"])
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise AIUnavailableError(
                f"{self.provider} returned an unreadable payload: {type(error).__name__}",
                self.provider,
            ) from error
