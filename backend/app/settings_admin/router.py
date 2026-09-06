from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import BotSettingsRead, BotSettingsUpdate
from app.security import require_panel_token
from app.settings_admin.service import BotSettingsService

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: SessionDep, settings: SettingsDep) -> BotSettingsService:
    return BotSettingsService(session, settings)


ServiceDep = Annotated[BotSettingsService, Depends(get_service)]


@router.get("", response_model=BotSettingsRead)
async def read_settings(service: ServiceDep) -> BotSettingsRead:
    return await service.read()


@router.patch("", response_model=BotSettingsRead)
async def update_settings(payload: BotSettingsUpdate, service: ServiceDep) -> BotSettingsRead:
    return await service.update(payload)
