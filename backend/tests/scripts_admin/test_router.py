from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.db.base import get_session
from app.main import create_app

TEMPLATE = "{name}, ваш «{product}» в «{category}» ещё актуален?"


def payload(**overrides: object) -> dict:
    base: dict = {
        "stage": 1,
        "variant_index": 1,
        "template_text": TEMPLATE,
        "active": True,
    }
    base.update(overrides)
    return base


async def create(client: AsyncClient, **overrides: object) -> dict:
    response = await client.post("/api/scripts", json=payload(**overrides))
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
        response = await anonymous.get("/api/scripts")

    assert response.status_code == 401


async def test_crud_roundtrip(client: AsyncClient) -> None:
    created = await create(client)
    script_id = created["id"]

    listed = await client.get("/api/scripts")
    assert [item["id"] for item in listed.json()] == [script_id]

    fetched = await client.get(f"/api/scripts/{script_id}")
    assert fetched.json()["template_text"] == TEMPLATE

    await create(client, variant_index=2, template_text="{name}, ещё актуально?")
    updated = await client.patch(
        f"/api/scripts/{script_id}", json={"template_text": "{name}, добрый день!"}
    )
    assert updated.status_code == 200
    assert updated.json()["template_text"] == "{name}, добрый день!"

    deleted = await client.delete(f"/api/scripts/{script_id}")
    assert deleted.status_code == 204


async def test_unknown_placeholder_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/scripts", json=payload(template_text="Здравствуйте, {seller}!")
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "{seller}" in response.json()["error"]["message"]


async def test_duplicate_slot_returns_409(client: AsyncClient) -> None:
    await create(client)

    response = await client.post("/api/scripts", json=payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_stage_holds_at_most_five_variants(client: AsyncClient) -> None:
    for variant in range(1, 6):
        await create(client, variant_index=variant, template_text=f"{{name}} вариант {variant}")

    response = await client.post("/api/scripts", json=payload(variant_index=1))

    assert response.status_code == 409


async def test_variant_index_above_five_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/scripts", json=payload(variant_index=6))

    assert response.status_code == 422


async def test_invalid_stage_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/scripts", json=payload(stage=4))

    assert response.status_code == 422


async def test_last_active_variant_cannot_be_disabled(client: AsyncClient) -> None:
    created = await create(client)

    response = await client.patch(f"/api/scripts/{created['id']}", json={"active": False})

    assert response.status_code == 409
    assert "without an active variant" in response.json()["error"]["message"]


async def test_last_active_variant_cannot_be_deleted(client: AsyncClient) -> None:
    created = await create(client)

    response = await client.delete(f"/api/scripts/{created['id']}")

    assert response.status_code == 409


async def test_variant_can_be_disabled_when_a_sibling_stays_active(
    client: AsyncClient,
) -> None:
    first = await create(client)
    await create(client, variant_index=2, template_text="{name}, ещё актуально?")

    response = await client.patch(f"/api/scripts/{first['id']}", json={"active": False})

    assert response.status_code == 200
    assert response.json()["active"] is False


async def test_filtering_by_stage(client: AsyncClient) -> None:
    await create(client, stage=1, variant_index=1)
    await create(client, stage=2, variant_index=1, template_text="{name}, напоминаю о себе")

    only_second = await client.get("/api/scripts", params={"stage": 2})

    assert [item["stage"] for item in only_second.json()] == [2]


async def test_coverage_reports_every_stage(client: AsyncClient) -> None:
    await create(client, stage=1, variant_index=1)
    await create(client, stage=1, variant_index=2, template_text="{name}, ещё актуально?")

    response = await client.get("/api/scripts/coverage")

    assert response.status_code == 200
    body = response.json()
    assert [row["stage"] for row in body] == [1, 2, 3]
    assert body[0]["variants"] == 2
    assert body[0]["active_variants"] == 2
    assert body[0]["free_slots"] == 3
    assert body[0]["ready"] is True
    assert body[1]["ready"] is False


async def test_unknown_script_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/scripts/999")

    assert response.status_code == 404
