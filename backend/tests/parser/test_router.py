from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.avito import get_avito_client
from app.clients.avito.fake import FakeAvitoClient
from app.db.base import get_session
from app.db.models import Category
from app.main import create_app
from tests.conftest import PANEL_HEADERS

BANI_SLUG = "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/banya-ASgBAgICAkRYlrI68I4O2o_OAQ"


@pytest.fixture
async def parser_client(
    engine: AsyncEngine, session: AsyncSession
) -> AsyncIterator[tuple[AsyncClient, Category]]:
    category = Category(
        name="Бани",
        avito_url_or_slug=BANI_SLUG,
        region="Россия",
        min_listings_per_seller=3,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)

    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_avito_client] = lambda: FakeAvitoClient()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=PANEL_HEADERS
    ) as client:
        yield client, category


async def test_run_endpoint_returns_stats(
    parser_client: tuple[AsyncClient, Category],
) -> None:
    client, category = parser_client

    response = await client.post(f"/api/parser/categories/{category.id}/run")

    assert response.status_code == 200
    body = response.json()
    assert body["category_id"] == category.id
    assert body["sellers_matched"] == 2
    assert body["sellers_created"] == 2
    assert body["listings_created"] == 3


async def test_run_endpoint_is_idempotent(
    parser_client: tuple[AsyncClient, Category],
) -> None:
    client, category = parser_client

    await client.post(f"/api/parser/categories/{category.id}/run")
    second = await client.post(f"/api/parser/categories/{category.id}/run")

    assert second.json()["sellers_created"] == 0
    assert second.json()["sellers_updated"] == 2

    sellers = await client.get("/api/parser/sellers")
    assert len(sellers.json()) == 2


async def test_run_endpoint_rejects_unknown_category(
    parser_client: tuple[AsyncClient, Category],
) -> None:
    client, _ = parser_client

    response = await client.post("/api/parser/categories/999/run")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_sellers_endpoint_filters_by_category(
    parser_client: tuple[AsyncClient, Category],
) -> None:
    client, category = parser_client
    await client.post(f"/api/parser/categories/{category.id}/run")

    matching = await client.get("/api/parser/sellers", params={"category_id": category.id})
    other = await client.get("/api/parser/sellers", params={"category_id": category.id + 99})

    assert len(matching.json()) == 2
    assert other.json() == []
    assert all(item["listings_count"] >= 3 for item in matching.json())


async def test_parser_requires_panel_token(
    engine: AsyncEngine,
) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/parser/sellers")

    assert response.status_code == 401
