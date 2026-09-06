from datetime import UTC, datetime
from typing import NamedTuple

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.analysis import ReplyAnalysisService
from app.clients.ai.base import (
    AIAnalysisRequest,
    AIAnalysisResponse,
    AIUnavailableError,
    AIVariationRequest,
    AIVariationResponse,
)
from app.config import get_settings
from app.db.models import (
    Account,
    Category,
    MessageLog,
    MessageStatus,
    Reply,
    Seller,
    SellerStatus,
)
from app.domain.schemas import ReplyCreate
from app.errors import ConflictError, NotFoundError


class ScriptedAnalysisAI:
    provider = "scripted"

    def __init__(
        self,
        sentiment: str = "neutral",
        confidence: float = 0.9,
        error: Exception | None = None,
    ) -> None:
        self.sentiment = sentiment
        self.confidence = confidence
        self.error = error
        self.calls: list[AIAnalysisRequest] = []

    async def rewrite(self, request: AIVariationRequest) -> AIVariationResponse:
        raise NotImplementedError

    async def analyze_reply(self, request: AIAnalysisRequest) -> AIAnalysisResponse:
        validated = AIAnalysisRequest.model_validate(request)
        self.calls.append(validated)
        if self.error is not None:
            raise self.error
        return AIAnalysisResponse(sentiment=self.sentiment, confidence=self.confidence)  # type: ignore[arg-type]


class World(NamedTuple):
    seller: Seller
    other_seller: Seller
    log: MessageLog
    other_log: MessageLog


async def build_world(session: AsyncSession) -> World:
    category = Category(
        name="Бани",
        avito_url_or_slug="rossiya/bani",
        region="Россия",
        min_listings_per_seller=3,
    )
    session.add(category)
    await session.flush()

    account = Account(login="acc-1", session_storage_path="data/acc-1.json", daily_limit=15)
    session.add(account)
    await session.flush()

    sellers: list[Seller] = []
    logs: list[MessageLog] = []
    for index in (1, 2):
        seller = Seller(
            avito_seller_id=f"seller-{index}",
            name=f"Продавец {index}",
            profile_url=f"https://www.avito.ru/brands/seller-{index}",
            listings_count=4,
            region="Москва",
            category_id=category.id,
            status=SellerStatus.CONTACTED,
        )
        session.add(seller)
        await session.flush()
        sellers.append(seller)

        log = MessageLog(
            seller_id=seller.id,
            account_id=account.id,
            stage=1,
            variant_used=1,
            final_text="Здравствуйте!",
            sent_at=datetime.now(UTC),
            status=MessageStatus.SENT,
        )
        session.add(log)
        await session.flush()
        logs.append(log)

    await session.commit()
    for row in (*sellers, *logs):
        await session.refresh(row)

    return World(sellers[0], sellers[1], logs[0], logs[1])


def make_service(session: AsyncSession, ai: object) -> ReplyAnalysisService:
    return ReplyAnalysisService(session, ai, get_settings())  # type: ignore[arg-type]


def payload(world: World, **overrides: object) -> ReplyCreate:
    base: dict[str, object] = {
        "seller_id": world.seller.id,
        "message_log_id": world.log.id,
        "reply_text": "Да, расскажите подробнее",
    }
    base.update(overrides)
    return ReplyCreate(**base)  # type: ignore[arg-type]


async def count_replies(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Reply)) or 0


async def test_confident_interest_promotes_the_seller(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI("interested", 0.9)

    result = await make_service(session, ai).register(payload(world))

    assert result.reply.ai_sentiment == "interested"
    assert result.reply.ai_confidence == 0.9
    assert result.reply.analyzed_at is not None
    assert result.seller_status == "interested"
    assert result.status_changed is True
    assert result.provider == "scripted"


async def test_confident_refusal_rejects_the_seller(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI("negative", 0.95)

    result = await make_service(session, ai).register(payload(world, reply_text="Не пишите мне"))

    assert result.seller_status == "rejected"
    assert result.status_changed is True


async def test_neutral_reply_keeps_the_status(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI("neutral", 1.0)

    result = await make_service(session, ai).register(payload(world, reply_text="Здравствуйте"))

    assert result.seller_status == "contacted"
    assert result.status_changed is False
    assert result.reply.ai_sentiment == "neutral"


async def test_low_confidence_does_not_move_the_seller(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI("interested", 0.3)

    result = await make_service(session, ai).register(payload(world))

    assert result.seller_status == "contacted"
    assert result.status_changed is False
    assert result.reply.ai_confidence == 0.3


async def test_delivered_lead_is_never_downgraded(session: AsyncSession) -> None:
    world = await build_world(session)
    world.seller.status = SellerStatus.LEAD
    await session.commit()
    ai = ScriptedAnalysisAI("negative", 1.0)

    result = await make_service(session, ai).register(payload(world))

    assert result.seller_status == "lead"
    assert result.status_changed is False


async def test_refusal_is_sticky(session: AsyncSession) -> None:
    world = await build_world(session)
    world.seller.status = SellerStatus.REJECTED
    await session.commit()
    ai = ScriptedAnalysisAI("interested", 1.0)

    result = await make_service(session, ai).register(payload(world))

    assert result.seller_status == "rejected"
    assert result.status_changed is False


async def test_analyzing_twice_has_one_effect(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI("interested", 0.9)
    service = make_service(session, ai)

    first = await service.register(payload(world))
    second = await service.analyze(first.reply.id)

    assert len(ai.calls) == 1
    assert second.already_analyzed is True
    assert second.reply.analyzed_at == first.reply.analyzed_at
    assert second.seller_status == "interested"
    assert await count_replies(session) == 1


async def test_same_external_id_is_ingested_once(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI("interested", 0.9)
    service = make_service(session, ai)

    first = await service.register(payload(world, external_id="avito-msg-1"))
    second = await service.register(payload(world, external_id="avito-msg-1"))

    assert await count_replies(session) == 1
    assert len(ai.calls) == 1
    assert second.reply.id == first.reply.id
    assert second.already_analyzed is True


async def test_unavailable_ai_keeps_the_reply_unanalyzed(session: AsyncSession) -> None:
    world = await build_world(session)
    ai = ScriptedAnalysisAI(error=AIUnavailableError("both providers down", "chain", 503))

    result = await make_service(session, ai).register(payload(world))

    assert await count_replies(session) == 1
    assert result.reply.ai_sentiment is None
    assert result.reply.analyzed_at is None
    assert result.seller_status == "contacted"
    assert "both providers down" in (result.reason or "")


async def test_reply_can_be_analyzed_after_the_model_recovers(session: AsyncSession) -> None:
    world = await build_world(session)
    down = ScriptedAnalysisAI(error=AIUnavailableError("down", "chain", 503))
    stored = await make_service(session, down).register(payload(world))

    healthy = ScriptedAnalysisAI("interested", 0.9)
    result = await make_service(session, healthy).analyze(stored.reply.id)

    assert result.reply.ai_sentiment == "interested"
    assert result.seller_status == "interested"
    assert result.already_analyzed is False
    assert await count_replies(session) == 1


async def test_message_log_of_another_seller_is_rejected(session: AsyncSession) -> None:
    world = await build_world(session)

    with pytest.raises(ConflictError):
        await make_service(session, ScriptedAnalysisAI()).register(
            payload(world, message_log_id=world.other_log.id)
        )


async def test_unknown_seller_raises_not_found(session: AsyncSession) -> None:
    world = await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, ScriptedAnalysisAI()).register(payload(world, seller_id=999))


async def test_unknown_message_log_raises_not_found(session: AsyncSession) -> None:
    world = await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, ScriptedAnalysisAI()).register(
            payload(world, message_log_id=999)
        )


async def test_analyzing_an_unknown_reply_raises_not_found(session: AsyncSession) -> None:
    await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, ScriptedAnalysisAI()).analyze(999)


async def test_list_replies_filters_by_seller(session: AsyncSession) -> None:
    world = await build_world(session)
    service = make_service(session, ScriptedAnalysisAI("neutral", 0.9))

    await service.register(payload(world))
    await service.register(
        ReplyCreate(
            seller_id=world.other_seller.id,
            message_log_id=world.other_log.id,
            reply_text="Спасибо, не надо",
        )
    )

    assert len(await service.list_replies()) == 2
    only_first = await service.list_replies(world.seller.id)
    assert [row.seller_id for row in only_first] == [world.seller.id]
