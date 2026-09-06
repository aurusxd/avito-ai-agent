from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.domain.schemas import ScriptCreate, ScriptRead, ScriptUpdate, StageCoverage
from app.scripts_admin.service import ScriptService
from app.security import require_panel_token

router = APIRouter(
    prefix="/scripts",
    tags=["scripts"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_service(session: SessionDep) -> ScriptService:
    return ScriptService(session)


ServiceDep = Annotated[ScriptService, Depends(get_service)]


@router.get("", response_model=list[ScriptRead])
async def list_scripts(
    service: ServiceDep,
    stage: Annotated[int | None, Query(ge=1, le=3)] = None,
) -> list[ScriptRead]:
    return await service.list_scripts(stage)


@router.get("/coverage", response_model=list[StageCoverage])
async def get_coverage(service: ServiceDep) -> list[StageCoverage]:
    return await service.coverage()


@router.get("/{script_id}", response_model=ScriptRead)
async def get_script(script_id: int, service: ServiceDep) -> ScriptRead:
    return await service.get(script_id)


@router.post("", response_model=ScriptRead, status_code=status.HTTP_201_CREATED)
async def create_script(payload: ScriptCreate, service: ServiceDep) -> ScriptRead:
    return await service.create(payload)


@router.patch("/{script_id}", response_model=ScriptRead)
async def update_script(script_id: int, payload: ScriptUpdate, service: ServiceDep) -> ScriptRead:
    return await service.update(script_id, payload)


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script(script_id: int, service: ServiceDep) -> None:
    await service.delete(script_id)
