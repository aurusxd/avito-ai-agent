import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.accounts.login_service import LoginService, reset_login_runs
from app.clients.avito.auth_factory import get_auth_client
from app.clients.avito.fake_auth import BROKEN_PROXY, FakeAvitoAuthClient
from app.config import Settings, get_settings
from app.db.base import get_session
from app.db.models import Account
from app.domain.schemas import LoginStartRequest
from app.errors import AppError, ConflictError, NotFoundError
from app.main import create_app

PROXY = "http://user:pass@proxy.example:10986"
VIEW_URL = "http://localhost:6080/vnc.html"


@pytest.fixture(autouse=True)
def clean_registry():
    reset_login_runs()
    yield
    reset_login_runs()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return get_settings().model_copy(
        update={
            "sessions_dir": str(tmp_path / "sessions"),
            "vnc_enabled": True,
            "vnc_public_url": VIEW_URL,
        }
    )


def make_service(session, client: FakeAvitoAuthClient, settings: Settings) -> LoginService:
    return LoginService(session, client, settings)


def request(**overrides: object) -> LoginStartRequest:
    base: dict[str, object] = {"login": "operator-1", "proxy_url": PROXY, "daily_limit": 15}
    base.update(overrides)
    return LoginStartRequest(**base)  # type: ignore[arg-type]


async def count_accounts(session) -> int:
    return await session.scalar(select(func.count()).select_from(Account)) or 0


async def test_start_opens_a_browser_and_waits_for_the_operator(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())

    assert started.status == "waiting_for_operator"
    assert started.remote_view_url == VIEW_URL
    assert auth.opened is True
    assert auth.proxy_url == PROXY
    assert await count_accounts(session) == 0


async def test_confirm_saves_the_session_the_operator_created(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())
    done = await service.confirm(started.session_id)

    assert done.status == "done"
    assert done.account_id is not None
    assert done.remote_view_url is None
    assert auth.closed is True

    account = await session.get(Account, done.account_id)
    assert account is not None
    assert account.login == "operator-1"
    assert account.proxy_url == PROXY
    assert account.session_storage_path.endswith("operator-1.storage.json")


async def test_confirm_before_signing_in_keeps_waiting(session, settings) -> None:
    auth = FakeAvitoAuthClient(signs_in_after=2)
    service = make_service(session, auth, settings)

    started = await service.start(request())

    early = await service.confirm(started.session_id)
    assert early.status == "waiting_for_operator"
    assert early.hint is not None
    assert await count_accounts(session) == 0

    done = await service.confirm(started.session_id)
    assert done.status == "done"
    assert auth.checks == 2


async def test_no_credentials_are_accepted_by_the_request_model() -> None:
    fields = set(LoginStartRequest.model_fields)

    assert "password" not in fields
    assert fields == {"login", "proxy_url", "daily_limit"}


async def test_broken_proxy_fails_and_closes_the_browser(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request(proxy_url=BROKEN_PROXY))

    assert started.status == "failed"
    assert auth.closed is True
    assert await count_accounts(session) == 0


async def test_start_refuses_when_the_remote_view_is_off(session, settings) -> None:
    blind = settings.model_copy(update={"vnc_enabled": False})

    with pytest.raises(AppError):
        await make_service(session, FakeAvitoAuthClient(), blind).start(request())


async def test_duplicate_login_is_rejected_before_the_browser_starts(session, settings) -> None:
    session.add(
        Account(
            login="operator-1",
            session_storage_path="data/sessions/operator-1.storage.json",
            daily_limit=15,
        )
    )
    await session.commit()

    auth = FakeAvitoAuthClient()

    with pytest.raises(ConflictError):
        await make_service(session, auth, settings).start(request())

    assert auth.opened is False


async def test_confirm_is_rejected_once_the_session_is_terminal(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), settings)

    started = await service.start(request())
    await service.confirm(started.session_id)

    with pytest.raises(ConflictError):
        await service.confirm(started.session_id)


async def test_cancel_closes_the_browser(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())
    cancelled = await service.cancel(started.session_id)

    assert cancelled.status == "failed"
    assert auth.closed is True


async def test_unknown_session_raises_not_found(session, settings) -> None:
    with pytest.raises(NotFoundError):
        await make_service(session, FakeAvitoAuthClient(), settings).state("nope")


async def test_waiting_session_carries_a_screenshot(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), settings)

    started = await service.start(request())

    assert started.has_screenshot is True
    assert service.screenshot(started.session_id) == b"fake-png"


async def test_manual_login_over_http(engine: AsyncEngine, settings: Settings) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    auth = FakeAvitoAuthClient(signs_in_after=2)

    async def override_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_auth_client] = lambda: auth
    app.dependency_overrides[get_settings] = lambda: settings

    headers = {"X-Panel-Token": "test-token"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        started = await client.post(
            "/api/accounts/login", json={"login": "operator-http", "proxy_url": None}
        )
        assert started.status_code == 201
        body = started.json()
        assert body["status"] == "waiting_for_operator"
        assert body["remote_view_url"] == VIEW_URL
        session_id = body["session_id"]

        waiting = await client.post(f"/api/accounts/login/{session_id}/confirm")
        assert waiting.json()["status"] == "waiting_for_operator"

        done = await client.post(f"/api/accounts/login/{session_id}/confirm")
        assert done.status_code == 200
        assert done.json()["status"] == "done"

        listed = await client.get("/api/accounts")
        assert [row["login"] for row in listed.json()] == ["operator-http"]


async def test_login_requires_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.post("/api/accounts/login", json={"login": "x"})

    assert response.status_code == 401


async def test_api_refuses_a_password_field(engine: AsyncEngine, settings: Settings) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_auth_client] = lambda: FakeAvitoAuthClient()
    app.dependency_overrides[get_settings] = lambda: settings

    headers = {"X-Panel-Token": "test-token"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        response = await client.post(
            "/api/accounts/login", json={"login": "nope", "password": "secret"}
        )

    assert response.status_code == 422
    assert "secret" not in response.text
