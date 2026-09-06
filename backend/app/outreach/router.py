from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito import get_avito_client
from app.clients.avito.base import AvitoClient
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import MessageLogRead, OutreachRequest, OutreachResult
from app.outreach.service import OutreachService
from app.security import require_panel_token

router = APIRouter(
    prefix="/outreach",
    tags=["outreach"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ClientDep = Annotated[AvitoClient, Depends(get_avito_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: SessionDep, client: ClientDep, settings: SettingsDep) -> OutreachService:
    return OutreachService(session, client, settings)


ServiceDep = Annotated[OutreachService, Depends(get_service)]


@router.post("/send", response_model=OutreachResult)
async def send_message(payload: OutreachRequest, service: ServiceDep) -> OutreachResult:
    return await service.send(payload)


@router.get("/messages", response_model=list[MessageLogRead])
async def list_messages(service: ServiceDep, seller_id: int | None = None) -> list[MessageLogRead]:
    return await service.list_messages(seller_id)
