from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.base import get_session
from app.main import create_app

PAYLOAD = {
    "name": "Бани",
    "avito_url_or_slug": "rossiya/bani",
    "region": "Россия",
    "min_listings_per_seller": 3,
    "enabled": True,
}


async def test_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/categories")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_crud_roundtrip(client: AsyncClient) -> None:
    created = await client.post("/api/categories", json=PAYLOAD)
    assert created.status_code == 201
    category_id = created.json()["id"]

    listed = await client.get("/api/categories")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [category_id]

    fetched = await client.get(f"/api/categories/{category_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Бани"

    updated = await client.patch(
        f"/api/categories/{category_id}", json={"enabled": False, "min_listings_per_seller": 5}
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["min_listings_per_seller"] == 5

    deleted = await client.delete(f"/api/categories/{category_id}")
    assert deleted.status_code == 204
    assert (await client.get("/api/categories")).json() == []


async def test_get_missing_category_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/categories/999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_duplicate_name_returns_409(client: AsyncClient) -> None:
    assert (await client.post("/api/categories", json=PAYLOAD)).status_code == 201

    response = await client.post("/api/categories", json=PAYLOAD)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_invalid_payload_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/categories", json={**PAYLOAD, "name": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
