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
        response = await anonymous.get("/api/dashboard/stats")

    assert response.status_code == 401


async def test_empty_database_returns_zeroes(client: AsyncClient) -> None:
    response = await client.get("/api/dashboard/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["sellers_total"] == 0
    assert body["leads_total"] == 0
    assert body["messages_sent"] == 0
    assert [row["stage"] for row in body["stages"]] == [1, 2, 3]
    assert all(row["sent"] == 0 for row in body["stages"])


async def test_stats_reflect_the_pipeline(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)

    response = await client.get("/api/dashboard/stats")

    body = response.json()
    assert body["sellers_total"] == 2
    assert body["sellers_interested"] == 1
    assert body["replies_total"] == 1
    assert body["replies_analyzed"] == 1
    assert body["messages_sent"] == 2
    assert body["stages"][0]["sent"] == 2
    assert body["accounts_active"] == 1


async def test_stats_count_delivered_leads(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)
    await add_reply(session, world)

    await client.post("/api/leads/deliver")
    body = (await client.get("/api/dashboard/stats")).json()

    assert body["leads_total"] == 1
    assert body["leads_delivered"] == 1
    assert body["sellers_interested"] == 0


async def test_stats_expose_the_bot_state(client: AsyncClient) -> None:
    await client.patch("/api/settings", json={"schedule": {"paused": True}})

    body = (await client.get("/api/dashboard/stats")).json()

    assert body["paused"] is True
    assert body["window_open_now"] is False
    assert "paused" in body["closed_reason"]


async def test_stats_report_rotation_capacity(client: AsyncClient, session: AsyncSession) -> None:
    await build_world(session)

    body = (await client.get("/api/dashboard/stats")).json()

    assert body["capacity_today"] == 15
    assert body["accounts_blocked"] == 0
