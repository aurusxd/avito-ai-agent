from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import get_session
from app.main import create_app
from tests.ai_pipeline.test_analysis import build_world


async def test_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/ai/replies")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_registering_a_reply_classifies_it(
    client: AsyncClient, session: AsyncSession
) -> None:
    world = await build_world(session)

    response = await client.post(
        "/api/ai/replies",
        json={
            "seller_id": world.seller.id,
            "message_log_id": world.log.id,
            "reply_text": "Да, интересно, расскажите",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["reply"]["ai_sentiment"] == "interested"
    assert body["seller_status"] == "interested"
    assert body["status_changed"] is True
    assert body["provider"] == "fake"


async def test_negative_reply_rejects_the_seller(
    client: AsyncClient, session: AsyncSession
) -> None:
    world = await build_world(session)

    response = await client.post(
        "/api/ai/replies",
        json={
            "seller_id": world.seller.id,
            "message_log_id": world.log.id,
            "reply_text": "Нет, не пишите мне больше",
        },
    )

    assert response.status_code == 201
    assert response.json()["seller_status"] == "rejected"


async def test_reanalyzing_returns_the_stored_verdict(
    client: AsyncClient, session: AsyncSession
) -> None:
    world = await build_world(session)

    created = await client.post(
        "/api/ai/replies",
        json={
            "seller_id": world.seller.id,
            "message_log_id": world.log.id,
            "reply_text": "Да, интересно",
        },
    )
    reply_id = created.json()["reply"]["id"]

    again = await client.post(f"/api/ai/replies/{reply_id}/analyze")

    assert again.status_code == 200
    assert again.json()["already_analyzed"] is True
    assert again.json()["reply"]["analyzed_at"] == created.json()["reply"]["analyzed_at"]


async def test_list_replies_filters_by_seller(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)

    await client.post(
        "/api/ai/replies",
        json={
            "seller_id": world.seller.id,
            "message_log_id": world.log.id,
            "reply_text": "Здравствуйте",
        },
    )

    listed = await client.get("/api/ai/replies", params={"seller_id": world.seller.id})

    assert listed.status_code == 200
    assert [row["seller_id"] for row in listed.json()] == [world.seller.id]


async def test_mismatched_message_log_returns_409(
    client: AsyncClient, session: AsyncSession
) -> None:
    world = await build_world(session)

    response = await client.post(
        "/api/ai/replies",
        json={
            "seller_id": world.seller.id,
            "message_log_id": world.other_log.id,
            "reply_text": "Да",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_unknown_seller_returns_404(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)

    response = await client.post(
        "/api/ai/replies",
        json={"seller_id": 999, "message_log_id": world.log.id, "reply_text": "Да"},
    )

    assert response.status_code == 404


async def test_empty_reply_text_returns_422(client: AsyncClient, session: AsyncSession) -> None:
    world = await build_world(session)

    response = await client.post(
        "/api/ai/replies",
        json={"seller_id": world.seller.id, "message_log_id": world.log.id, "reply_text": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
