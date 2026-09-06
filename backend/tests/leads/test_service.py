from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram.base import NotifierUnavailableError
from app.clients.telegram.fake import FakeNotifier
from app.config import get_settings
from app.db.models import Lead, Reply, Seller, SellerStatus, Sentiment
from app.errors import NotFoundError
from app.leads.service import LeadService
from tests.ai_pipeline.test_analysis import World, build_world

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


async def add_reply(
    session: AsyncSession,
    world: World,
    *,
    sentiment: Sentiment = Sentiment.INTERESTED,
    text: str = "Да, интересно",
    minutes: int = 0,
) -> Reply:
    reply = Reply(
        seller_id=world.seller.id,
        message_log_id=world.log.id,
        reply_text=text,
        received_at=NOW + timedelta(minutes=minutes),
        ai_sentiment=sentiment,
        ai_confidence=0.9,
        analyzed_at=NOW + timedelta(minutes=minutes),
    )
    session.add(reply)
    world.seller.status = SellerStatus.INTERESTED
    await session.commit()
    await session.refresh(reply)
    return reply


def make_service(session: AsyncSession, notifier: FakeNotifier) -> LeadService:
    return LeadService(session, notifier, get_settings())


async def count_leads(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Lead)) or 0


async def test_interested_seller_becomes_a_delivered_lead(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    notifier = FakeNotifier()

    run = await make_service(session, notifier).deliver_pending()

    assert run.candidates == 1
    assert run.delivered == 1
    assert len(notifier.sent) == 1

    await session.refresh(world.seller)
    assert world.seller.status == SellerStatus.LEAD
    assert await count_leads(session) == 1


async def test_notification_carries_the_conversation(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world, text="Да, расскажите про сроки")
    notifier = FakeNotifier()

    await make_service(session, notifier).deliver_pending()

    notification = notifier.sent[0]
    assert notification.seller_name == world.seller.name
    assert notification.stage_reached == 1
    roles = [message.role for message in notification.conversation_history]
    assert roles == ["bot", "seller"]
    assert notification.conversation_history[-1].text == "Да, расскажите про сроки"
    assert notification.conversation_history[0].text == "Здравствуйте!"


async def test_delivery_is_idempotent(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    notifier = FakeNotifier()
    service = make_service(session, notifier)

    first = await service.deliver_pending()
    second = await service.deliver_pending()

    assert first.delivered == 1
    assert second.candidates == 0
    assert second.delivered == 0
    assert len(notifier.sent) == 1
    assert await count_leads(session) == 1


async def test_repeated_delivery_for_the_same_seller_is_skipped(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    notifier = FakeNotifier()
    service = make_service(session, notifier)

    await service.deliver_seller(world.seller.id)
    again = await service.deliver_seller(world.seller.id)

    assert again.already_delivered is True
    assert len(notifier.sent) == 1
    assert await count_leads(session) == 1


async def test_failed_delivery_keeps_the_seller_for_a_retry(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    notifier = FakeNotifier(
        failure=NotifierUnavailableError("telegram is down", "aiogram"), fail_times=1
    )
    service = make_service(session, notifier)

    failed = await service.deliver_pending()

    assert failed.failed == 1
    assert failed.delivered == 0
    assert await count_leads(session) == 0
    await session.refresh(world.seller)
    assert world.seller.status == SellerStatus.INTERESTED

    recovered = await service.deliver_pending()

    assert recovered.delivered == 1
    await session.refresh(world.seller)
    assert world.seller.status == SellerStatus.LEAD


async def test_seller_without_an_interested_reply_is_not_delivered(
    session: AsyncSession,
) -> None:
    world = await build_world(session)
    await add_reply(session, world, sentiment=Sentiment.NEUTRAL, text="Здравствуйте")
    notifier = FakeNotifier()

    run = await make_service(session, notifier).deliver_pending()

    assert run.candidates == 1
    assert run.delivered == 0
    assert notifier.sent == []


async def test_only_interested_sellers_are_candidates(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    world.seller.status = SellerStatus.CONTACTED
    await session.commit()
    notifier = FakeNotifier()

    run = await make_service(session, notifier).deliver_pending()

    assert run.candidates == 0
    assert notifier.sent == []


async def test_latest_interested_reply_triggers_the_lead(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world, text="Первый ответ", minutes=0)
    newest = await add_reply(session, world, text="Второй ответ", minutes=30)
    notifier = FakeNotifier()

    result = await make_service(session, notifier).deliver_seller(world.seller.id)

    assert result.reply_id == newest.id


async def test_unknown_seller_raises_not_found(session: AsyncSession) -> None:
    await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, FakeNotifier()).deliver_seller(999)


async def test_list_leads_returns_stored_history(session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    service = make_service(session, FakeNotifier())
    await service.deliver_pending()

    leads = await service.list_leads()

    assert len(leads) == 1
    assert leads[0].seller_id == world.seller.id
    assert leads[0].sent_to_telegram_at is not None
    assert len(leads[0].conversation_history) == 2


async def test_seller_without_listings_falls_back_to_the_profile_url(
    session: AsyncSession,
) -> None:
    world = await build_world(session)
    await add_reply(session, world)
    notifier = FakeNotifier()

    await make_service(session, notifier).deliver_pending()

    seller = await session.get(Seller, world.seller.id)
    assert seller is not None
    assert notifier.sent[0].listing_url == seller.profile_url
