from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.telegram import get_notifier
from app.clients.telegram.base import Notifier
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import LeadDeliveryResult, LeadRead, LeadsRunResult
from app.leads.service import LeadService
from app.security import require_panel_token

router = APIRouter(
    prefix="/leads",
    tags=["leads"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: SessionDep, notifier: NotifierDep, settings: SettingsDep) -> LeadService:
    return LeadService(session, notifier, settings)


ServiceDep = Annotated[LeadService, Depends(get_service)]


@router.get("", response_model=list[LeadRead])
async def list_leads(service: ServiceDep) -> list[LeadRead]:
    return await service.list_leads()


@router.post("/deliver", response_model=LeadsRunResult)
async def deliver_pending(service: ServiceDep) -> LeadsRunResult:
    return await service.deliver_pending()


@router.post("/sellers/{seller_id}/deliver", response_model=LeadDeliveryResult)
async def deliver_seller(seller_id: int, service: ServiceDep) -> LeadDeliveryResult:
    return await service.deliver_seller(seller_id)
