from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito import get_avito_client
from app.clients.avito.base import AvitoClient
from app.db.base import get_session
from app.domain.schemas import ParserRunResult, SellerRead
from app.parser.service import ParserService
from app.security import require_panel_token

router = APIRouter(
    prefix="/parser",
    tags=["parser"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ClientDep = Annotated[AvitoClient, Depends(get_avito_client)]


def get_service(session: SessionDep, client: ClientDep) -> ParserService:
    return ParserService(session, client)


ServiceDep = Annotated[ParserService, Depends(get_service)]


@router.post("/categories/{category_id}/run", response_model=ParserRunResult)
async def run_parser(category_id: int, service: ServiceDep) -> ParserRunResult:
    return await service.run(category_id)


@router.get("/sellers", response_model=list[SellerRead])
async def list_sellers(service: ServiceDep, category_id: int | None = None) -> list[SellerRead]:
    return await service.list_sellers(category_id)
