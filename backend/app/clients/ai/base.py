from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.domain.schemas import SentimentLiteral


class AIVariationRequest(BaseModel):
    template_text: str = Field(min_length=1)
    seller_name: str = Field(min_length=1)
    product: str = Field(min_length=1)
    category: str = Field(min_length=1)


class AIVariationResponse(BaseModel):
    unique_text: str = Field(min_length=1)


class AIAnalysisRequest(BaseModel):
    reply_text: str = Field(min_length=1)


class AIAnalysisResponse(BaseModel):
    sentiment: SentimentLiteral
    confidence: float = Field(ge=0.0, le=1.0)


@runtime_checkable
class AIClient(Protocol):
    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse: ...

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse: ...
