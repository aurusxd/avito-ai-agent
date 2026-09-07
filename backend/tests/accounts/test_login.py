import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.accounts.login_service import LoginService, reset_login_runs
from app.clients.avito.auth_factory import get_auth_client
from app.clients.avito.fake_auth import CAPTCHA_LOGIN, VALID_CODE, FakeAvitoAuthClient
from app.config import Settings, get_settings
from app.db.base import get_session
from app.db.models import Account
from app.domain.schemas import LoginStartRequest
from app.errors import ConflictError, NotFoundError
from app.main import create_app

PASSWORD = "super-secret-password"


@pytest.fixture(autouse=True)
def clean_registry():
    reset_login_runs()
    yield
    reset_login_runs()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return get_settings().model_copy(update={"sessions_dir": str(tmp_path / "sessions")})


def make_service(session, client: FakeAvitoAuthClient, settings: Settings) -> LoginService:
    return LoginService(session, client, settings)


def request(**overrides: object) -> LoginStartRequest:
    base: dict[str, object] = {
        "login": "operator-1",
        "password": PASSWORD,
        "proxy_url": "http://user:pass@proxy.example:10986",
        "daily_limit": 15,
    }
    base.update(overrides)
    return LoginStartRequest(**base)  # type: ignore[arg-type]


async def count_accounts(session) -> int:
    return await session.scalar(select(func.count()).select_from(Account)) or 0


async def test_happy_path_creates_the_account(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())
    assert started.status == "code_required"
    assert started.hint is not None
    assert auth.saw_password is True
    assert auth.proxy_url == "http://user:pass@proxy.example:10986"

    done = await service.submit_code(started.session_id, VALID_CODE)

    assert done.status == "done"
    assert done.account_id is not None
    assert auth.closed is True
    assert await count_accounts(session) == 1

    account = await session.get(Account, done.account_id)
    assert account is not None
    assert account.login == "operator-1"
    assert account.proxy_url == "http://user:pass@proxy.example:10986"
    assert account.session_storage_path.endswith("operator-1.storage.json")


async def test_password_is_never_stored_or_returned(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())
    done = await service.submit_code(started.session_id, VALID_CODE)

    assert PASSWORD not in done.model_dump_json()

    account = await session.get(Account, done.account_id)
    assert account is not None
    dumped = " ".join(str(value) for value in vars(account).values())
    assert PASSWORD not in dumped


async def test_password_is_masked_in_the_request_model() -> None:
    payload = request()

    assert PASSWORD not in repr(payload)
    assert PASSWORD not in str(payload)
    assert payload.password.get_secret_value() == PASSWORD


async def test_wrong_code_keeps_the_session_open(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())
    retry = await service.submit_code(started.session_id, "000000")

    assert retry.status == "code_required"
    assert retry.hint is not None
    assert await count_accounts(session) == 0

    done = await service.submit_code(started.session_id, VALID_CODE)
    assert done.status == "done"
    assert auth.code_attempts == 2


async def test_bad_password_fails_and_closes_the_browser(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request(password="wrong"))

    assert started.status == "failed"
    assert auth.closed is True
    assert await count_accounts(session) == 0


async def test_captcha_stops_with_a_screenshot(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request(login=CAPTCHA_LOGIN))

    assert started.status == "captcha_required"
    assert started.has_screenshot is True
    assert service.screenshot(started.session_id) == b"fake-png"
    assert await count_accounts(session) == 0


async def test_code_is_rejected_when_the_session_does_not_expect_one(session, settings) -> None:
    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request(login=CAPTCHA_LOGIN))

    with pytest.raises(ConflictError):
        await service.submit_code(started.session_id, VALID_CODE)


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

    assert auth.login is None


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


async def test_code_step_also_carries_a_screenshot(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), settings)

    started = await service.start(request())

    assert started.status == "code_required"
    assert started.has_screenshot is True
    assert service.screenshot(started.session_id) == b"fake-png"


async def test_session_without_a_screenshot_raises_not_found(session, settings) -> None:
    class Blind(FakeAvitoAuthClient):
        async def screenshot(self) -> bytes | None:
            return None

    service = make_service(session, Blind(), settings)
    started = await service.start(request())

    assert started.has_screenshot is False
    with pytest.raises(NotFoundError):
        service.screenshot(started.session_id)


async def test_login_flow_over_http(engine: AsyncEngine, settings: Settings) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    auth = FakeAvitoAuthClient()

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
            "/api/accounts/login",
            json={"login": "operator-http", "password": PASSWORD, "proxy_url": None},
        )
        assert started.status_code == 201
        assert started.json()["status"] == "code_required"
        assert PASSWORD not in started.text
        session_id = started.json()["session_id"]

        state = await client.get(f"/api/accounts/login/{session_id}")
        assert state.status_code == 200
        assert state.json()["status"] == "code_required"

        done = await client.post(
            f"/api/accounts/login/{session_id}/code", json={"code": VALID_CODE}
        )
        assert done.status_code == 200
        assert done.json()["status"] == "done"
        assert done.json()["account_id"] is not None

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
        response = await anonymous.post("/api/accounts/login", json={"login": "x", "password": "y"})

    assert response.status_code == 401


def vnc_settings(base: Settings) -> Settings:
    return base.model_copy(
        update={"vnc_enabled": True, "vnc_public_url": "http://localhost:6080/vnc.html"}
    )


async def test_remote_view_is_offered_only_while_a_person_is_needed(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), vnc_settings(settings))

    waiting = await service.start(request(login=CAPTCHA_LOGIN))
    assert waiting.status == "captcha_required"
    assert waiting.remote_view_url == "http://localhost:6080/vnc.html"


async def test_remote_view_is_hidden_once_the_session_is_done(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), vnc_settings(settings))

    started = await service.start(request())
    assert started.remote_view_url is not None

    done = await service.submit_code(started.session_id, VALID_CODE)

    assert done.status == "done"
    assert done.remote_view_url is None


async def test_remote_view_stays_off_when_vnc_is_disabled(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), settings)

    started = await service.start(request(login=CAPTCHA_LOGIN))

    assert started.status == "captcha_required"
    assert started.remote_view_url is None


async def test_remote_view_needs_a_public_url(session, settings) -> None:
    tuned = settings.model_copy(update={"vnc_enabled": True, "vnc_public_url": ""})
    service = make_service(session, FakeAvitoAuthClient(), tuned)

    started = await service.start(request(login=CAPTCHA_LOGIN))

    assert started.remote_view_url is None


async def test_resume_continues_after_a_person_cleared_the_check(session, settings) -> None:
    auth = FakeAvitoAuthClient(captcha_rounds=1)
    service = make_service(session, auth, settings)

    started = await service.start(request(login=CAPTCHA_LOGIN))
    assert started.status == "captcha_required"

    # the operator is still stuck on the check
    again = await service.resume(started.session_id)
    assert again.status == "captcha_required"

    # now the check is cleared and the flow walks on
    moved = await service.resume(started.session_id)
    assert moved.status == "code_required"
    assert auth.resume_calls == 2

    done = await service.submit_code(started.session_id, VALID_CODE)
    assert done.status == "done"


async def test_resume_wipes_the_password_once_the_session_ends(session, settings) -> None:
    from app.accounts.login_service import _runs

    auth = FakeAvitoAuthClient()
    service = make_service(session, auth, settings)

    started = await service.start(request())
    assert _runs[started.session_id].password == PASSWORD

    done = await service.submit_code(started.session_id, VALID_CODE)

    assert done.status == "done"
    assert _runs[started.session_id].password is None


async def test_resume_is_rejected_once_the_session_is_terminal(session, settings) -> None:
    service = make_service(session, FakeAvitoAuthClient(), settings)

    started = await service.start(request())
    await service.submit_code(started.session_id, VALID_CODE)

    with pytest.raises(ConflictError):
        await service.resume(started.session_id)


async def test_resume_over_http(engine: AsyncEngine, settings: Settings) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    auth = FakeAvitoAuthClient(captcha_rounds=1)

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
            "/api/accounts/login",
            json={"login": CAPTCHA_LOGIN, "password": PASSWORD, "proxy_url": None},
        )
        session_id = started.json()["session_id"]
        assert started.json()["status"] == "captcha_required"

        stuck = await client.post(f"/api/accounts/login/{session_id}/resume")
        assert stuck.json()["status"] == "captcha_required"

        moved = await client.post(f"/api/accounts/login/{session_id}/resume")
        assert moved.status_code == 200
        assert moved.json()["status"] == "code_required"
        assert PASSWORD not in moved.text
