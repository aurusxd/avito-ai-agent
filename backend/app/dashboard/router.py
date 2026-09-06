from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.dashboard.service import DashboardService
from app.db.base import get_session
from app.domain.schemas import DashboardStats
from app.security import require_panel_token

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: SessionDep, settings: SettingsDep) -> DashboardService:
    return DashboardService(session, settings)


ServiceDep = Annotated[DashboardService, Depends(get_service)]


@router.get("/stats", response_model=DashboardStats)
async def get_stats(service: ServiceDep) -> DashboardStats:
    return await service.stats()
