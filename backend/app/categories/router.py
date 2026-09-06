from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories.service import CategoryService
from app.db.base import get_session
from app.domain.schemas import CategoryCreate, CategoryDTO, CategoryRead, CategoryUpdate
from app.security import require_panel_token

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
    dependencies=[Depends(require_panel_token)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_service(session: SessionDep) -> CategoryService:
    return CategoryService(session)


ServiceDep = Annotated[CategoryService, Depends(get_service)]


@router.get("", response_model=list[CategoryRead])
async def list_categories(service: ServiceDep, region: str | None = None) -> list[CategoryRead]:
    return await service.list_categories(region)


@router.get("/regions", response_model=list[str])
async def list_regions(service: ServiceDep) -> list[str]:
    return await service.regions()


@router.get("/{category_id}", response_model=CategoryDTO)
async def get_category(category_id: int, service: ServiceDep) -> CategoryDTO:
    return await service.get(category_id)


@router.post("", response_model=CategoryDTO, status_code=status.HTTP_201_CREATED)
async def create_category(payload: CategoryCreate, service: ServiceDep) -> CategoryDTO:
    return await service.create(payload)


@router.patch("/{category_id}", response_model=CategoryDTO)
async def update_category(
    category_id: int, payload: CategoryUpdate, service: ServiceDep
) -> CategoryDTO:
    return await service.update(category_id, payload)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, service: ServiceDep) -> None:
    await service.delete(category_id)
