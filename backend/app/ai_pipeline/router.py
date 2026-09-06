from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.service import VariationService
from app.clients.ai import get_ai_client
from app.clients.ai.base import AIClient
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import VariationRequest, VariationResult
from app.security import require_panel_token

router = APIRouter(
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ClientDep = Annotated[AIClient, Depends(get_ai_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: SessionDep, client: ClientDep, settings: SettingsDep) -> VariationService:
    return VariationService(session, client, settings)


ServiceDep = Annotated[VariationService, Depends(get_service)]


@router.post("/variations/preview", response_model=VariationResult)
async def preview_variation(payload: VariationRequest, service: ServiceDep) -> VariationResult:
    return await service.preview(payload)
