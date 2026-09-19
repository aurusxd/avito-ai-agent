from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.base import get_session
from app.main import create_app


async def test_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/settings")

    assert response.status_code == 401


async def test_defaults_are_created_on_first_read(client: AsyncClient) -> None:
    response = await client.get("/api/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["window_start"] == 9
    assert body["window_end"] == 21
    assert body["weekdays_enabled"] == [0, 1, 2, 3, 4]
    assert body["paused"] is False
    assert body["delay_min_minutes"] == 5
    assert body["delay_max_minutes"] == 15
    assert body["daily_limit"] == 15
    assert body["timezone"] == "Europe/Moscow"


async def test_schedule_update_is_persisted(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/settings",
        json={"schedule": {"window_start": 10, "window_end": 19, "weekdays_enabled": [0, 1, 2]}},
    )

    assert response.status_code == 200
    assert response.json()["window_start"] == 10
    assert response.json()["window_end"] == 19
    assert response.json()["weekdays_enabled"] == [0, 1, 2]

    again = await client.get("/api/settings")
    assert again.json()["window_start"] == 10


async def test_pause_toggles_without_touching_the_window(client: AsyncClient) -> None:
    paused = await client.patch("/api/settings", json={"schedule": {"paused": True}})

    assert paused.json()["paused"] is True
    assert paused.json()["window_open_now"] is False
    assert paused.json()["next_window_at"] is None
    assert "паузе" in paused.json()["closed_reason"]
    assert paused.json()["window_start"] == 9

    resumed = await client.patch("/api/settings", json={"schedule": {"paused": False}})
    assert resumed.json()["paused"] is False


async def test_panel_cannot_widen_the_delay_beyond_policy(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/settings",
        json={"limits": {"delay_min_minutes": 1, "delay_max_minutes": 600}},
    )

    assert response.status_code == 200
    assert response.json()["delay_min_minutes"] == 5
    assert response.json()["delay_max_minutes"] == 15


async def test_panel_cannot_widen_the_rotation_beyond_policy(client: AsyncClient) -> None:
    response = await client.patch("/api/settings", json={"limits": {"account_rotation_size": 9}})

    assert response.status_code == 200
    assert response.json()["account_rotation_size"] == 3


async def test_reversed_window_is_repaired(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/settings", json={"schedule": {"window_start": 20, "window_end": 8}}
    )

    assert response.status_code == 200
    assert response.json()["window_start"] < response.json()["window_end"]


async def test_invalid_hour_returns_422(client: AsyncClient) -> None:
    response = await client.patch("/api/settings", json={"schedule": {"window_start": 30}})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_window_state_is_reported(client: AsyncClient) -> None:
    response = await client.patch(
        "/api/settings",
        json={
            "schedule": {
                "window_start": 0,
                "window_end": 24,
                "weekdays_enabled": [0, 1, 2, 3, 4, 5, 6],
            }
        },
    )

    body = response.json()
    assert body["window_open_now"] is True
    assert body["closed_reason"] is None
    assert body["next_window_at"] is not None
