from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.service import AccountService
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import AccountCreate, AccountRead, AccountUpdate, RotationPreview
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


@router.get("", response_model=list[AccountRead])
async def list_accounts(service: ServiceDep) -> list[AccountRead]:
    return await service.list()


@router.get("/rotation", response_model=RotationPreview)
async def get_rotation(service: ServiceDep) -> RotationPreview:
    return await service.rotation_preview()


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
