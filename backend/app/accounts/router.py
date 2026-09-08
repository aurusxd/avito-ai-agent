from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.login_service import LoginService
from app.accounts.proxy_service import ProxyService
from app.accounts.service import AccountService
from app.clients.avito.auth_factory import get_auth_client
from app.clients.avito.base import AvitoAuthClient
from app.clients.proxy.base import ProxyProvider
from app.clients.proxy.factory import get_proxy_provider
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    LoginSessionRead,
    LoginStartRequest,
    ProxyBalanceRead,
    ProxyIssueRequest,
    ProxyIssueResult,
    RotationPreview,
)
from app.security import require_panel_token

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: SessionDep, settings: SettingsDep) -> AccountService:
    return AccountService(session, settings)


ServiceDep = Annotated[AccountService, Depends(get_service)]
AuthClientDep = Annotated[AvitoAuthClient, Depends(get_auth_client)]


def get_login_service(
    session: SessionDep, client: AuthClientDep, settings: SettingsDep
) -> LoginService:
    return LoginService(session, client, settings)


LoginDep = Annotated[LoginService, Depends(get_login_service)]
ProxyProviderDep = Annotated[ProxyProvider, Depends(get_proxy_provider)]


def get_proxy_service(provider: ProxyProviderDep, settings: SettingsDep) -> ProxyService:
    return ProxyService(provider, settings)


ProxyDep = Annotated[ProxyService, Depends(get_proxy_service)]


@router.get("", response_model=list[AccountRead])
async def list_accounts(service: ServiceDep) -> list[AccountRead]:
    return await service.list()


@router.get("/rotation", response_model=RotationPreview)
async def get_rotation(service: ServiceDep) -> RotationPreview:
    return await service.rotation_preview()


@router.post(
    "/login",
    response_model=LoginSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def start_login(payload: LoginStartRequest, service: LoginDep) -> LoginSessionRead:
    return await service.start(payload)


@router.get("/login/{session_id}", response_model=LoginSessionRead)
async def login_state(session_id: str, service: LoginDep) -> LoginSessionRead:
    return await service.state(session_id)


@router.post("/login/{session_id}/confirm", response_model=LoginSessionRead)
async def confirm_login(session_id: str, service: LoginDep) -> LoginSessionRead:
    return await service.confirm(session_id)


@router.post("/login/{session_id}/cancel", response_model=LoginSessionRead)
async def cancel_login(session_id: str, service: LoginDep) -> LoginSessionRead:
    return await service.cancel(session_id)


@router.get("/login/{session_id}/screenshot")
async def login_screenshot(session_id: str, service: LoginDep) -> Response:
    return Response(content=service.screenshot(session_id), media_type="image/png")


@router.get("/proxy/balances", response_model=list[ProxyBalanceRead])
async def proxy_balances(service: ProxyDep) -> list[ProxyBalanceRead]:
    return await service.balances()


@router.get("/proxy/options", response_model=list[str])
async def proxy_options(service: ProxyDep, field: str, country: str | None = None) -> list[str]:
    return await service.options(field, country)


@router.post("/proxy/issue", response_model=ProxyIssueResult)
async def issue_proxy(payload: ProxyIssueRequest, service: ProxyDep) -> ProxyIssueResult:
    return await service.issue(payload)


@router.get("/{account_id}", response_model=AccountRead)
async def get_account(account_id: int, service: ServiceDep) -> AccountRead:
    return await service.get(account_id)


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(payload: AccountCreate, service: ServiceDep) -> AccountRead:
    return await service.create(payload)


@router.patch("/{account_id}", response_model=AccountRead)
async def update_account(
    account_id: int, payload: AccountUpdate, service: ServiceDep
) -> AccountRead:
    return await service.update(account_id, payload)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, service: ServiceDep) -> None:
    await service.delete(account_id)
