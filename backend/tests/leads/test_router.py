from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import get_session
from app.main import create_app
from tests.ai_pipeline.test_analysis import build_world
from tests.leads.test_service import add_reply


async def test_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/leads")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_deliver_pending_creates_a_lead(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)

    response = await client.post("/api/leads/deliver")

    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == 1
    assert body["delivered"] == 1

    listed = await client.get("/api/leads")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["sent_to_telegram_at"] is not None


async def test_delivering_twice_is_idempotent(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)

    await client.post("/api/leads/deliver")
    second = await client.post("/api/leads/deliver")

    assert second.json()["delivered"] == 0
    assert len((await client.get("/api/leads")).json()) == 1


async def test_deliver_single_seller(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)

    response = await client.post(f"/api/leads/sellers/{world.seller.id}/deliver")

    assert response.status_code == 200
    assert response.json()["delivered"] is True


async def test_unknown_seller_returns_404(client: AsyncClient, session: AsyncSession) -> None:
    await build_world(session)

    response = await client.post("/api/leads/sellers/999/deliver")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_inbox_poll_endpoint_reports_stats(
    client: AsyncClient, session: AsyncSession
) -> None:
    await build_world(session)

    response = await client.post("/api/ai/inbox/poll", json={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert "fetched" in body
    assert "ingested" in body
    assert body["block_kind"] == "none"
