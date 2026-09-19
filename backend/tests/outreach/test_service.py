from datetime import UTC, datetime, timedelta
from random import Random
from typing import NamedTuple

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai.base import AIClient
from app.clients.ai.fake import FakeAIClient
from app.clients.avito.base import AvitoBlockedError
from app.clients.avito.fake import FakeAvitoClient
from app.config import get_settings
from app.db.models import (
    Account,
    AccountStatus,
    Category,
    Listing,
    MessageLog,
    ScheduleSettings,
    Script,
    Seller,
)
from app.db.models import SellerStatus as SellerStatusEnum
from app.domain.schemas import OutreachRequest
from app.errors import NotFoundError
from app.outreach.service import OutreachService

TEMPLATE = "{name}, ваш «{product}» в «{category}» ещё актуален?"


class World(NamedTuple):
    category: Category
    seller: Seller
    accounts: list[Account]


async def build_world(session: AsyncSession, *, accounts: int = 1) -> World:
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
    session.add(
        ScheduleSettings(
            window_start=0,
            window_end=24,
            weekdays_enabled=[0, 1, 2, 3, 4, 5, 6],
            paused=False,
        )
    )

    created: list[Account] = []
    for index in range(1, accounts + 1):
        account = Account(
            login=f"acc-{index}",
            session_storage_path=f"data/sessions/acc-{index}.json",
            daily_limit=15,
        )
        session.add(account)
        created.append(account)

    await session.commit()
    for account in created:
        await session.refresh(account)
    await session.refresh(seller)

    return World(category=category, seller=seller, accounts=created)


def make_service(
    session: AsyncSession,
    client: FakeAvitoClient,
    ai: AIClient | None = None,
) -> OutreachService:
    return OutreachService(session, client, get_settings(), ai or FakeAIClient(), rng=Random(7))


async def count_logs(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(MessageLog)) or 0


async def test_send_renders_template_and_records_log(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    client = FakeAvitoClient()
    service = make_service(session, client)

    result = await service.send(OutreachRequest(seller_id=seller.id, stage=1))

    assert result.status == "sent"
    assert result.variant_used == 1
    assert result.block_kind == "none"
    assert result.already_sent is False

    assert len(client.sent) == 1
    _, _, text = client.sent[0]
    assert text == "Артём, ваш «Баня-бочка под ключ» в «Бани» ещё актуален?"
    assert "{name}" not in text

    await session.refresh(seller)
    assert seller.status == SellerStatusEnum.CONTACTED

    account = world.accounts[0]
    await session.refresh(account)
    assert account.daily_message_count == 1


async def test_same_job_twice_sends_once(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    account = world.accounts[0]
    client = FakeAvitoClient()
    service = make_service(session, client)
    job = OutreachRequest(seller_id=seller.id, stage=1, account_id=account.id)

    first = await service.send(job)
    second = await service.send(job)

    assert first.status == "sent"
    assert first.already_sent is False
    assert second.already_sent is True
    assert second.message_log_id == first.message_log_id
    assert len(client.sent) == 1
    assert await count_logs(session) == 1

    await session.refresh(account)
    assert account.daily_message_count == 1


async def test_stages_are_tracked_separately(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    session.add(Script(stage=2, variant_index=1, template_text=TEMPLATE, active=True))
    await session.commit()

    client = FakeAvitoClient()
    service = make_service(session, client)

    assert (await service.send(OutreachRequest(seller_id=seller.id, stage=1))).status == "sent"
    assert (await service.send(OutreachRequest(seller_id=seller.id, stage=2))).status == "sent"
    assert await count_logs(session) == 2


@pytest.mark.parametrize(
    ("block_kind", "expected_status", "cooled_down"),
    [
        ("captcha", AccountStatus.PAUSED, True),
        ("rate_limited", AccountStatus.PAUSED, True),
        ("forbidden", AccountStatus.BANNED, False),
        ("auth_required", AccountStatus.BANNED, False),
    ],
)
async def test_block_pulls_account_out_of_rotation(
    session: AsyncSession,
    block_kind: str,
    expected_status: AccountStatus,
    cooled_down: bool,
) -> None:
    world = await build_world(session)
    seller = world.seller
    account = world.accounts[0]
    client = FakeAvitoClient(
        block=AvitoBlockedError("avito blocked the request", block_kind),  # type: ignore[arg-type]
        block_times=5,
    )
    service = make_service(session, client)

    result = await service.send(OutreachRequest(seller_id=seller.id, stage=1))

    assert result.status == "failed"
    assert result.block_kind == block_kind
    assert client.sent == []

    await session.refresh(account)
    assert account.status == expected_status
    assert account.last_block_kind is not None
    assert account.last_block_kind.value == block_kind
    assert account.last_block_at is not None
    assert account.daily_message_count == 0
    assert (account.paused_until is not None) is cooled_down

    log = await session.scalar(select(MessageLog))
    assert log is not None
    assert log.status.value == "failed"


async def test_blocked_account_is_not_retried_in_the_same_run(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    session.add(Script(stage=2, variant_index=1, template_text=TEMPLATE, active=True))
    await session.commit()

    client = FakeAvitoClient(block=AvitoBlockedError("captcha shown", "captcha"), block_times=1)
    service = make_service(session, client)

    blocked = await service.send(OutreachRequest(seller_id=seller.id, stage=1))
    assert blocked.block_kind == "captcha"

    follow_up = await service.send(OutreachRequest(seller_id=seller.id, stage=2))

    assert follow_up.status == "skipped"
    assert follow_up.account_id is None
    assert client.sent == []


async def test_account_returns_after_cooldown(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    account = world.accounts[0]

    account.status = AccountStatus.PAUSED
    account.paused_until = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()

    client = FakeAvitoClient()
    service = make_service(session, client)

    result = await service.send(OutreachRequest(seller_id=seller.id, stage=1))

    assert result.status == "sent"
    await session.refresh(account)
    assert account.status == AccountStatus.ACTIVE
    assert account.paused_until is None


async def test_exhausted_daily_limit_skips_without_sending(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    account = world.accounts[0]
    account.daily_message_count = account.daily_limit
    await session.commit()

    client = FakeAvitoClient()
    service = make_service(session, client)

    result = await service.send(OutreachRequest(seller_id=seller.id, stage=1))

    assert result.status == "skipped"
    assert result.reason is not None
    assert client.sent == []
    assert await count_logs(session) == 0


async def test_rotation_picks_the_least_loaded_account(session: AsyncSession) -> None:
    world = await build_world(session, accounts=3)
    seller = world.seller
    accounts = world.accounts
    accounts[0].daily_message_count = 9
    accounts[1].daily_message_count = 2
    accounts[2].daily_message_count = 7
    await session.commit()

    client = FakeAvitoClient()
    service = make_service(session, client)

    result = await service.send(OutreachRequest(seller_id=seller.id, stage=1))

    assert result.account_id == accounts[1].id


async def test_missing_seller_raises_not_found(session: AsyncSession) -> None:
    await build_world(session)
    service = make_service(session, FakeAvitoClient())

    with pytest.raises(NotFoundError):
        await service.send(OutreachRequest(seller_id=999, stage=1))


async def test_missing_script_skips(session: AsyncSession) -> None:
    world = await build_world(session)
    seller = world.seller
    script = await session.scalar(select(Script))
    assert script is not None
    script.active = False
    await session.commit()

    client = FakeAvitoClient()
    service = make_service(session, client)

    result = await service.send(OutreachRequest(seller_id=seller.id, stage=1))

    assert result.status == "skipped"
    assert client.sent == []
    assert await count_logs(session) == 0


async def test_send_is_skipped_while_the_bot_is_paused(session: AsyncSession) -> None:
    world = await build_world(session)
    schedule = await session.scalar(select(ScheduleSettings))
    assert schedule is not None
    schedule.paused = True
    await session.commit()

    client = FakeAvitoClient()
    result = await make_service(session, client).send(
        OutreachRequest(seller_id=world.seller.id, stage=1)
    )

    assert result.status == "skipped"
    assert "паузе" in (result.reason or "")
    assert client.sent == []
    assert await count_logs(session) == 0


async def test_send_is_skipped_outside_the_window(session: AsyncSession) -> None:
    world = await build_world(session)
    schedule = await session.scalar(select(ScheduleSettings))
    assert schedule is not None
    schedule.weekdays_enabled = []
    await session.commit()

    client = FakeAvitoClient()
    result = await make_service(session, client).send(
        OutreachRequest(seller_id=world.seller.id, stage=1)
    )

    assert result.status == "skipped"
    assert client.sent == []
