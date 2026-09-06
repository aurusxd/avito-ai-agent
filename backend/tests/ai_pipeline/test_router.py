from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.base import get_session
from app.main import create_app
from tests.ai_pipeline.test_service import RENDERED, build_world


async def test_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.post(
            "/api/ai/variations/preview", json={"seller_id": 1, "stage": 1}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_preview_returns_a_variation(client: AsyncClient, session) -> None:
    seller = await build_world(session)

    response = await client.post(
        "/api/ai/variations/preview", json={"seller_id": seller.id, "stage": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["seller_id"] == seller.id
    assert body["stage"] == 1
    assert body["variant_used"] == 1
    assert body["template_text"] == RENDERED
    assert body["final_text"] == RENDERED
    assert body["source"] == "ai"


async def test_unknown_seller_returns_404(client: AsyncClient, session) -> None:
    await build_world(session)

    response = await client.post("/api/ai/variations/preview", json={"seller_id": 999, "stage": 1})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_stage_without_script_returns_404(client: AsyncClient, session) -> None:
    seller = await build_world(session)

    response = await client.post(
        "/api/ai/variations/preview", json={"seller_id": seller.id, "stage": 3}
    )

    assert response.status_code == 404


async def test_invalid_stage_returns_422(client: AsyncClient, session) -> None:
    seller = await build_world(session)

    response = await client.post(
        "/api/ai/variations/preview", json={"seller_id": seller.id, "stage": 9}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unknown_variant_returns_404(client: AsyncClient, session) -> None:
    seller = await build_world(session)

    response = await client.post(
        "/api/ai/variations/preview",
        json={"seller_id": seller.id, "stage": 1, "variant_index": 5},
    )

    assert response.status_code == 404
