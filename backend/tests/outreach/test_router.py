from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.clients.avito import get_avito_client
from app.clients.avito.base import AvitoBlockedError
from app.clients.avito.fake import FakeAvitoClient
from app.db.base import get_session
from app.main import create_app
from tests.conftest import PANEL_HEADERS
from tests.outreach.test_service import build_world

PROXY = "http://user:s3cret@proxy.example.com:8000"


def build_client(engine: AsyncEngine, avito: FakeAvitoClient) -> AsyncClient:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_avito_client] = lambda: avito
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=PANEL_HEADERS
    )


async def test_send_requires_panel_token(engine: AsyncEngine) -> None:
    async with build_client(engine, FakeAvitoClient()) as client:
        client.headers.pop("X-Panel-Token")
        response = await client.post("/api/outreach/send", json={"seller_id": 1, "stage": 1})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_send_and_list_messages(engine: AsyncEngine, session: AsyncSession) -> None:
    world = await build_world(session)
    seller_id = world.seller.id
    avito = FakeAvitoClient()

    async with build_client(engine, avito) as client:
        sent = await client.post("/api/outreach/send", json={"seller_id": seller_id, "stage": 1})
        repeat = await client.post("/api/outreach/send", json={"seller_id": seller_id, "stage": 1})
        messages = await client.get("/api/outreach/messages")

    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert repeat.json()["already_sent"] is True
    assert len(avito.sent) == 1

    body = messages.json()
    assert len(body) == 1
    assert body[0]["stage"] == 1
    assert body[0]["status"] == "sent"


async def test_send_reports_block_kind(engine: AsyncEngine, session: AsyncSession) -> None:
    world = await build_world(session)
    seller_id = world.seller.id
    avito = FakeAvitoClient(block=AvitoBlockedError("captcha shown", "captcha"), block_times=1)

    async with build_client(engine, avito) as client:
        response = await client.post(
            "/api/outreach/send", json={"seller_id": seller_id, "stage": 1}
        )
        accounts = await client.get("/api/accounts")

    body = response.json()
    assert body["status"] == "failed"
    assert body["block_kind"] == "captcha"

    account = accounts.json()[0]
    assert account["status"] == "paused"
    assert account["last_block_kind"] == "captcha"
    assert account["paused_until"] is not None


async def test_invalid_stage_returns_422(engine: AsyncEngine) -> None:
    async with build_client(engine, FakeAvitoClient()) as client:
        response = await client.post("/api/outreach/send", json={"seller_id": 1, "stage": 9})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_account_proxy_is_masked_in_the_api(engine: AsyncEngine) -> None:
    async with build_client(engine, FakeAvitoClient()) as client:
        created = await client.post(
            "/api/accounts",
            json={
                "login": "acc-proxy",
                "session_storage_path": "data/sessions/acc-proxy.json",
                "daily_limit": 15,
                "proxy_url": PROXY,
            },
        )

    body = created.json()
    assert created.status_code == 201
    assert body["has_proxy"] is True
    assert body["proxy_url"] == "http://***@proxy.example.com:8000"
    assert "s3cret" not in created.text
