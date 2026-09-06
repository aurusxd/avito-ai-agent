import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.service import FALLBACK_CATEGORY, FALLBACK_PRODUCT, VariationService
from app.clients.ai.base import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIUnavailableError,
    AIVariationRequest,
    AIVariationResponse,
)
from app.clients.ai.fake import FakeAIClient
from app.config import get_settings
from app.db.models import Category, Listing, Script, Seller
from app.domain.schemas import VariationRequest
from app.errors import NotFoundError

TEMPLATE = "{name}, ваш «{product}» в «{category}» ещё актуален?"
RENDERED = "Артём, ваш «Баня-бочка под ключ» в «Бани» ещё актуален?"


class ScriptedAI:
    provider = "scripted"

    def __init__(self, answer: str | None = None, error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[AIVariationRequest] = []

    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse:
        validated = AIVariationRequest.model_validate(request)
        self.calls.append(validated)
        if self.error is not None:
            raise self.error
        return AIVariationResponse(unique_text=self.answer or "ok")

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        raise NotImplementedError


async def build_world(session: AsyncSession, *, with_listing: bool = True) -> Seller:
    category = Category(
        name="Бани",
        avito_url_or_slug="rossiya/bani",
        region="Россия",
        min_listings_per_seller=3,
    )
    session.add(category)
    await session.flush()

    seller = Seller(
        avito_seller_id="seed-seller-1",
        name="Артём",
        profile_url="https://www.avito.ru/brands/seed-seller-1",
        listings_count=4,
        region="Москва",
        category_id=category.id,
    )
    session.add(seller)
    await session.flush()

    if with_listing:
        session.add(
            Listing(
                seller_id=seller.id,
                avito_listing_id="seed-listing-1",
                title="Баня-бочка под ключ",
                url="https://www.avito.ru/moskva/seed-listing-1",
                category_id=category.id,
                region="Москва",
                price=320000,
            )
        )

    session.add(Script(stage=1, variant_index=1, template_text=TEMPLATE, active=True))
    await session.commit()
    await session.refresh(seller)
    return seller


def make_service(session: AsyncSession, client: object) -> VariationService:
    return VariationService(session, client, get_settings())  # type: ignore[arg-type]


async def test_accepted_rewrite_replaces_the_template(session: AsyncSession) -> None:
    seller = await build_world(session)
    ai = ScriptedAI(answer="Артём, добрый день! Баня-бочка ещё в работе?")

    result = await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert result.source == "ai"
    assert result.final_text == "Артём, добрый день! Баня-бочка ещё в работе?"
    assert result.template_text == RENDERED
    assert result.provider == "scripted"
    assert result.variant_used == 1
    assert result.reason is None


async def test_ai_receives_raw_template_and_seller_context(session: AsyncSession) -> None:
    seller = await build_world(session)
    ai = ScriptedAI(answer="Артём, актуально?")

    await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert len(ai.calls) == 1
    call = ai.calls[0]
    assert call.template_text == TEMPLATE
    assert call.seller_name == "Артём"
    assert call.product == "Баня-бочка под ключ"
    assert call.category == "Бани"


async def test_unavailable_ai_falls_back_to_the_rendered_template(session: AsyncSession) -> None:
    seller = await build_world(session)
    ai = ScriptedAI(error=AIUnavailableError("both providers down", "chain", 503))

    result = await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert result.source == "template"
    assert result.final_text == RENDERED
    assert "both providers down" in (result.reason or "")


async def test_unresolved_placeholder_is_rejected(session: AsyncSession) -> None:
    seller = await build_world(session)
    ai = ScriptedAI(answer="Здравствуйте, {name}! Актуально?")

    result = await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert result.source == "template"
    assert result.final_text == RENDERED
    assert result.reason == "unresolved_placeholder"


async def test_overlong_rewrite_is_rejected(session: AsyncSession) -> None:
    seller = await build_world(session)
    limit = get_settings().ai_max_variation_length
    ai = ScriptedAI(answer="а" * (limit + 1))

    result = await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert result.source == "template"
    assert result.final_text == RENDERED
    assert result.reason == "too_long"


async def test_empty_rewrite_is_rejected(session: AsyncSession) -> None:
    seller = await build_world(session)
    ai = ScriptedAI(answer="   ")

    result = await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert result.source == "template"
    assert result.reason == "empty"


async def test_seller_without_listings_uses_the_product_fallback(session: AsyncSession) -> None:
    seller = await build_world(session, with_listing=False)
    ai = ScriptedAI(answer="Артём, актуально?")

    await make_service(session, ai).preview(VariationRequest(seller_id=seller.id, stage=1))

    assert ai.calls[0].product == FALLBACK_PRODUCT
    assert ai.calls[0].category != FALLBACK_CATEGORY


async def test_fake_client_keeps_the_template_meaning(session: AsyncSession) -> None:
    seller = await build_world(session)

    result = await make_service(session, FakeAIClient()).preview(
        VariationRequest(seller_id=seller.id, stage=1)
    )

    assert result.final_text == RENDERED
    assert result.reason == "not_rewritten"
    assert result.source == "ai"


async def test_unknown_seller_raises_not_found(session: AsyncSession) -> None:
    await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, FakeAIClient()).preview(
            VariationRequest(seller_id=999, stage=1)
        )


async def test_stage_without_active_script_raises_not_found(session: AsyncSession) -> None:
    seller = await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, FakeAIClient()).preview(
            VariationRequest(seller_id=seller.id, stage=3)
        )


async def test_inactive_script_is_not_used(session: AsyncSession) -> None:
    seller = await build_world(session)
    script = await session.scalar(select(Script).where(Script.stage == 1))
    assert script is not None
    script.active = False
    await session.commit()

    with pytest.raises(NotFoundError):
        await make_service(session, FakeAIClient()).preview(
            VariationRequest(seller_id=seller.id, stage=1)
        )
