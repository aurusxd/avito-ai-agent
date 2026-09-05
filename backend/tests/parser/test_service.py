import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito.fake import FakeAvitoClient
from app.db.models import Category, Listing, Seller, SellerStatus
from app.db.seed import SEED_PARSER_RESULTS
from app.errors import NotFoundError
from app.parser.service import ParserService

BANI_SLUG = "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/banya-ASgBAgICAkRYlrI68I4O2o_OAQ"


async def make_category(session: AsyncSession, min_listings: int = 3) -> Category:
    category = Category(
        name="Бани",
        avito_url_or_slug=BANI_SLUG,
        region="Россия",
        min_listings_per_seller=min_listings,
        enabled=True,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_run_stores_matching_sellers_and_listings(session: AsyncSession) -> None:
    category = await make_category(session)
    service = ParserService(session, FakeAvitoClient())

    stats = await service.run(category.id)

    assert stats.sellers_matched == 2
    assert stats.sellers_created == 2
    assert stats.listings_created == 3
    assert await count(session, Seller) == 2
    assert await count(session, Listing) == 3

    stored = list(await session.scalars(select(Seller)))
    assert {s.avito_seller_id for s in stored} == {"seed-seller-1", "seed-seller-2"}
    assert all(s.category_id == category.id for s in stored)
    assert all(s.status is SellerStatus.NEW for s in stored)


async def test_run_skips_sellers_below_min_listings(session: AsyncSession) -> None:
    category = await make_category(session)
    service = ParserService(session, FakeAvitoClient())

    await service.run(category.id)

    ids = {s.avito_seller_id for s in await session.scalars(select(Seller))}
    assert "seed-seller-3" not in ids


async def test_run_threshold_is_taken_from_category(session: AsyncSession) -> None:
    category = await make_category(session, min_listings=5)
    service = ParserService(session, FakeAvitoClient())

    stats = await service.run(category.id)

    assert stats.sellers_created == 1
    ids = {s.avito_seller_id for s in await session.scalars(select(Seller))}
    assert ids == {"seed-seller-2"}


async def test_run_is_idempotent(session: AsyncSession) -> None:
    category = await make_category(session)
    service = ParserService(session, FakeAvitoClient())

    first = await service.run(category.id)
    second = await service.run(category.id)

    assert first.sellers_created == 2
    assert second.sellers_created == 0
    assert second.sellers_updated == 2
    assert second.listings_created == 0
    assert second.listings_updated == 3
    assert await count(session, Seller) == 2
    assert await count(session, Listing) == 3


async def test_rerun_keeps_seller_status(session: AsyncSession) -> None:
    category = await make_category(session)
    service = ParserService(session, FakeAvitoClient())
    await service.run(category.id)

    seller = await session.scalar(select(Seller).where(Seller.avito_seller_id == "seed-seller-1"))
    assert seller is not None
    seller.status = SellerStatus.CONTACTED
    await session.commit()

    await service.run(category.id)

    await session.refresh(seller)
    assert seller.status is SellerStatus.CONTACTED


async def test_rerun_refreshes_listings_count(session: AsyncSession) -> None:
    category = await make_category(session)
    await ParserService(session, FakeAvitoClient()).run(category.id)

    grown = [result.model_copy(deep=True) for result in SEED_PARSER_RESULTS]
    grown[0].seller.listings_count = 9
    await ParserService(session, FakeAvitoClient(results=grown)).run(category.id)

    seller = await session.scalar(select(Seller).where(Seller.avito_seller_id == "seed-seller-1"))
    assert seller is not None
    assert seller.listings_count == 9


async def test_run_rejects_unknown_category(session: AsyncSession) -> None:
    service = ParserService(session, FakeAvitoClient())

    with pytest.raises(NotFoundError):
        await service.run(999)


async def test_run_propagates_client_failure_without_partial_write(
    session: AsyncSession,
) -> None:
    category = await make_category(session)
    client = FakeAvitoClient(failure=TimeoutError("avito timeout"), fail_times=1)
    service = ParserService(session, client)

    with pytest.raises(TimeoutError):
        await service.run(category.id)

    assert await count(session, Seller) == 0
    assert await count(session, Listing) == 0

    stats = await service.run(category.id)
    assert stats.sellers_created == 2


async def test_list_sellers_filters_by_category(session: AsyncSession) -> None:
    first = await make_category(session)
    second = Category(
        name="Модульные дома",
        avito_url_or_slug="all/doma_dachi_kottedzhi",
        region="Россия",
        min_listings_per_seller=3,
    )
    session.add(second)
    await session.commit()
    await session.refresh(second)

    service = ParserService(session, FakeAvitoClient())
    await service.run(first.id)

    assert len(await service.list_sellers()) == 2
    assert len(await service.list_sellers(category_id=first.id)) == 2
    assert await service.list_sellers(category_id=second.id) == []


async def test_list_sellers_orders_by_listings_count(session: AsyncSession) -> None:
    category = await make_category(session)
    service = ParserService(session, FakeAvitoClient())
    await service.run(category.id)

    counts = [seller.listings_count for seller in await service.list_sellers()]

    assert counts == sorted(counts, reverse=True)
