from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.analysis import ReplyAnalysisService
from app.ai_pipeline.inbox import InboxService
from app.ai_pipeline.service import VariationService
from app.clients.ai import get_ai_client
from app.clients.ai.base import AIClient
from app.clients.avito import get_avito_client
from app.clients.avito.base import AvitoClient
from app.config import Settings, get_settings
from app.db.base import get_session
from app.domain.schemas import (
    InboxPollRequest,
    InboxPollResult,
    ReplyAnalysisResult,
    ReplyCreate,
    ReplyRead,
    VariationRequest,
    VariationResult,
)
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


def get_analysis_service(
    session: SessionDep, client: ClientDep, settings: SettingsDep
) -> ReplyAnalysisService:
    return ReplyAnalysisService(session, client, settings)


AnalysisDep = Annotated[ReplyAnalysisService, Depends(get_analysis_service)]
AvitoDep = Annotated[AvitoClient, Depends(get_avito_client)]


def get_inbox_service(
    session: SessionDep, avito: AvitoDep, analysis: AnalysisDep, settings: SettingsDep
) -> InboxService:
    return InboxService(session, avito, analysis, settings)


InboxDep = Annotated[InboxService, Depends(get_inbox_service)]


@router.post("/variations/preview", response_model=VariationResult)
async def preview_variation(payload: VariationRequest, service: ServiceDep) -> VariationResult:
    return await service.preview(payload)


@router.post(
    "/replies",
    response_model=ReplyAnalysisResult,
    status_code=status.HTTP_201_CREATED,
)
async def register_reply(payload: ReplyCreate, service: AnalysisDep) -> ReplyAnalysisResult:
    return await service.register(payload)


@router.post("/replies/{reply_id}/analyze", response_model=ReplyAnalysisResult)
async def analyze_reply(reply_id: int, service: AnalysisDep) -> ReplyAnalysisResult:
    return await service.analyze(reply_id)


@router.get("/replies", response_model=list[ReplyRead])
async def list_replies(service: AnalysisDep, seller_id: int | None = None) -> list[ReplyRead]:
    return await service.list_replies(seller_id)


@router.post("/inbox/poll", response_model=InboxPollResult)
async def poll_inbox(payload: InboxPollRequest, service: InboxDep) -> InboxPollResult:
    return await service.poll(payload)
