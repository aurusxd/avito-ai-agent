from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.analysis import ReplyAnalysisService
from app.ai_pipeline.inbox import InboxService
from app.clients.ai.fake import FakeAIClient
from app.clients.avito.base import AvitoBlockedError, IncomingReplyDTO
from app.clients.avito.fake import FakeAvitoClient
from app.config import get_settings
from app.db.models import Account, AccountStatus, Reply, Seller, SellerStatus
from app.domain.schemas import InboxPollRequest
from app.errors import NotFoundError
from tests.ai_pipeline.test_analysis import build_world

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def incoming(seller_key: str, text: str, external_id: str) -> IncomingReplyDTO:
    return IncomingReplyDTO(
        external_id=external_id,
        avito_seller_id=seller_key,
        text=text,
        received_at=NOW,
    )


def make_service(session: AsyncSession, avito: FakeAvitoClient) -> InboxService:
    settings = get_settings()
    analysis = ReplyAnalysisService(session, FakeAIClient(), settings)
    return InboxService(session, avito, analysis, settings)


async def count_replies(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Reply)) or 0


async def test_poll_ingests_and_classifies(session: AsyncSession) -> None:
    world = await build_world(session)
    avito = FakeAvitoClient(replies=[incoming("seller-1", "Да, интересно", "msg-1")])

    result = await make_service(session, avito).poll(InboxPollRequest())

    assert result.fetched == 1
    assert result.ingested == 1
    assert result.analyzed == 1
    assert result.unknown_sellers == 0
    assert await count_replies(session) == 1

    await session.refresh(world.seller)
    assert world.seller.status == SellerStatus.INTERESTED


async def test_polling_twice_ingests_once(session: AsyncSession) -> None:
    await build_world(session)
    avito = FakeAvitoClient(replies=[incoming("seller-1", "Да, интересно", "msg-1")])
    service = make_service(session, avito)

    first = await service.poll(InboxPollRequest())
    second = await service.poll(InboxPollRequest())

    assert first.ingested == 1
    assert second.ingested == 0
    assert second.duplicates == 1
    assert await count_replies(session) == 1


async def test_reply_from_an_unknown_seller_is_counted_not_stored(
    session: AsyncSession,
) -> None:
    await build_world(session)
    avito = FakeAvitoClient(replies=[incoming("seller-does-not-exist", "Да", "msg-9")])

    result = await make_service(session, avito).poll(InboxPollRequest())

    assert result.unknown_sellers == 1
    assert result.ingested == 0
    assert await count_replies(session) == 0


async def test_seller_without_a_sent_message_is_skipped(session: AsyncSession) -> None:
    world = await build_world(session)
    orphan = Seller(
        avito_seller_id="seller-orphan",
        name="Без переписки",
        profile_url="https://www.avito.ru/brands/seller-orphan",
        listings_count=3,
        region="Москва",
        category_id=world.seller.category_id,
    )
    session.add(orphan)
    await session.commit()

    avito = FakeAvitoClient(replies=[incoming("seller-orphan", "Да", "msg-3")])

    result = await make_service(session, avito).poll(InboxPollRequest())

    assert result.without_message_log == 1
    assert result.ingested == 0


async def test_block_pauses_the_account_and_reports_the_kind(session: AsyncSession) -> None:
    await build_world(session)
    avito = FakeAvitoClient(
        replies=[incoming("seller-1", "Да", "msg-1")],
        block=AvitoBlockedError("captcha shown", "captcha", 600),
        block_times=1,
    )

    result = await make_service(session, avito).poll(InboxPollRequest())

    assert result.block_kind == "captcha"
    assert result.ingested == 0
    assert "captcha" in (result.reason or "")

    account = await session.scalar(select(Account).where(Account.login == "acc-1"))
    assert account is not None
    assert account.status == AccountStatus.PAUSED
    assert account.last_block_kind is not None
    assert account.last_block_kind.value == "captcha"


async def test_poll_without_an_active_account_reports_the_reason(
    session: AsyncSession,
) -> None:
    await build_world(session)
    account = await session.scalar(select(Account).where(Account.login == "acc-1"))
    assert account is not None
    account.status = AccountStatus.BANNED
    await session.commit()

    result = await make_service(session, FakeAvitoClient(replies=[])).poll(InboxPollRequest())

    assert result.account_id is None
    assert result.reason is not None


async def test_unknown_account_raises_not_found(session: AsyncSession) -> None:
    await build_world(session)

    with pytest.raises(NotFoundError):
        await make_service(session, FakeAvitoClient(replies=[])).poll(
            InboxPollRequest(account_id=999)
        )


async def test_limit_is_passed_to_the_client(session: AsyncSession) -> None:
    await build_world(session)
    avito = FakeAvitoClient(
        replies=[
            incoming("seller-1", "Да", "msg-1"),
            incoming("seller-2", "Нет", "msg-2"),
        ]
    )

    result = await make_service(session, avito).poll(InboxPollRequest(limit=1))

    assert result.fetched == 1
