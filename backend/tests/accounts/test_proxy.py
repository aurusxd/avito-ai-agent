import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.accounts.proxy_service import ProxyService
from app.clients.proxy.base import ProxyGenerateRequest, ProxyProviderError
from app.clients.proxy.factory import get_proxy_provider
from app.clients.proxy.fake import FakeProxyProvider
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.proxy import proxy_settings
from app.domain.schemas import ProxyIssueRequest
from app.errors import AppError
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return get_settings()


def make_service(provider: FakeProxyProvider, settings: Settings) -> ProxyService:
    return ProxyService(provider, settings)


async def test_balances_report_gigabytes(settings) -> None:
    rows = await make_service(FakeProxyProvider(), settings).balances()

    residential = next(row for row in rows if row.proxy_type == "residential")
    assert residential.remaining_mb == 1000.0
    assert residential.remaining_gb == 0.977
    assert residential.traffic_ready is True


async def test_issue_returns_a_usable_sticky_url(settings) -> None:
    provider = FakeProxyProvider()

    issued = await make_service(provider, settings).issue(
        ProxyIssueRequest(country="RU", city="Moscow")
    )

    assert proxy_settings(issued.url) is not None
    assert issued.session_id == "fake0"
    assert issued.lifetime_minutes == settings.proxy_default_lifetime_minutes
    assert issued.country == "RU"

    sent = provider.requests[0]
    assert sent.session_type == "session"
    assert sent.quantity == 1
    assert sent.city == "Moscow"


async def test_issue_falls_back_to_the_configured_defaults(settings) -> None:
    provider = FakeProxyProvider()

    await make_service(provider, settings).issue(ProxyIssueRequest())

    sent = provider.requests[0]
    assert sent.country == settings.proxy_default_country
    assert sent.proxy_type == settings.proxy_default_type
    assert sent.lifetime_minutes == settings.proxy_default_lifetime_minutes


async def test_masked_url_hides_the_credentials(settings) -> None:
    issued = await make_service(FakeProxyProvider(), settings).issue(ProxyIssueRequest())

    assert "seedpass" not in issued.masked_url
    assert "seed_login" not in issued.masked_url
    assert "***" in issued.masked_url


async def test_provider_failure_becomes_an_app_error(settings) -> None:
    provider = FakeProxyProvider(failure=ProxyProviderError("provider is down"), fail_times=1)

    with pytest.raises(AppError):
        await make_service(provider, settings).balances()


async def test_empty_result_becomes_an_app_error(settings) -> None:
    with pytest.raises(AppError):
        await make_service(FakeProxyProvider(), settings).issue(ProxyIssueRequest(country="ZZ"))


async def test_lifetime_cannot_exceed_the_provider_limit() -> None:
    with pytest.raises(ValueError):
        ProxyGenerateRequest(lifetime_minutes=10_081)


async def test_proxy_endpoints_over_http(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    provider = FakeProxyProvider()

    async def override_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_proxy_provider] = lambda: provider

    headers = {"X-Panel-Token": "test-token"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        balances = await client.get("/api/accounts/proxy/balances")
        assert balances.status_code == 200
        assert any(row["proxy_type"] == "residential" for row in balances.json())

        options = await client.get("/api/accounts/proxy/options?field=country")
        assert options.status_code == 200
        assert "RU" in options.json()

        issued = await client.post(
            "/api/accounts/proxy/issue", json={"country": "RU", "city": "Moscow"}
        )
        assert issued.status_code == 200
        assert issued.json()["session_id"] == "fake0"


async def test_proxy_endpoints_require_the_panel_token(engine: AsyncEngine) -> None:
    app = create_app()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/accounts/proxy/balances")

    assert response.status_code == 401
