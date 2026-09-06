from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.base import get_session
from app.main import create_app

PAYLOAD = {
    "login": "operator-1",
    "session_storage_path": "data/sessions/operator-1.storage.json",
    "daily_limit": 15,
}


async def create_account(client: AsyncClient, **overrides: object) -> dict:
    response = await client.post("/api/accounts", json={**PAYLOAD, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


async def test_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/accounts")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_crud_roundtrip(client: AsyncClient) -> None:
    created = await create_account(client)
    account_id = created["id"]

    assert created["status"] == "active"
    assert created["daily_message_count"] == 0
    assert created["remaining_today"] == 15
    assert created["has_session"] is False

    listed = await client.get("/api/accounts")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [account_id]

    paused = await client.patch(f"/api/accounts/{account_id}", json={"status": "paused"})
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    deleted = await client.delete(f"/api/accounts/{account_id}")
    assert deleted.status_code == 204
    assert (await client.get("/api/accounts")).json() == []


async def test_missing_account_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/accounts/999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_duplicate_login_returns_409(client: AsyncClient) -> None:
    await create_account(client)

    response = await client.post("/api/accounts", json=PAYLOAD)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_panel_cannot_raise_daily_limit_above_policy(client: AsyncClient) -> None:
    response = await client.post("/api/accounts", json={**PAYLOAD, "daily_limit": 200})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    created = await create_account(client, daily_limit=10)
    raised = await client.patch(f"/api/accounts/{created['id']}", json={"daily_limit": 99})

    assert raised.status_code == 422


async def test_rotation_preview_reports_pool_and_next_account(client: AsyncClient) -> None:
    first = await create_account(client, login="acc-1", session_storage_path="data/a1.json")
    second = await create_account(client, login="acc-2", session_storage_path="data/a2.json")
    third = await create_account(client, login="acc-3", session_storage_path="data/a3.json")
    fourth = await create_account(client, login="acc-4", session_storage_path="data/a4.json")

    response = await client.get("/api/accounts/rotation")

    assert response.status_code == 200
    body = response.json()
    assert body["rotation_size"] == 3
    assert body["delay_min_minutes"] == 5
    assert body["delay_max_minutes"] == 15
    assert body["next_account_id"] == first["id"]
    assert body["capacity_today"] == 45

    in_rotation = [m["account_id"] for m in body["members"] if m["in_rotation"]]
    assert in_rotation == [first["id"], second["id"], third["id"]]
    assert fourth["id"] not in in_rotation


async def test_rotation_preview_skips_paused_accounts(client: AsyncClient) -> None:
    first = await create_account(client, login="acc-1", session_storage_path="data/a1.json")
    second = await create_account(client, login="acc-2", session_storage_path="data/a2.json")

    await client.patch(f"/api/accounts/{first['id']}", json={"status": "paused"})

    body = (await client.get("/api/accounts/rotation")).json()

    assert body["next_account_id"] == second["id"]
    assert body["capacity_today"] == 15
    members = {m["account_id"]: m for m in body["members"]}
    assert members[first["id"]]["in_rotation"] is False
    assert members[first["id"]]["available"] is False


async def test_rotation_preview_without_accounts(client: AsyncClient) -> None:
    body = (await client.get("/api/accounts/rotation")).json()

    assert body["next_account_id"] is None
    assert body["capacity_today"] == 0
    assert body["members"] == []
