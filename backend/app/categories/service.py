from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category
from app.domain.schemas import CategoryCreate, CategoryDTO, CategoryUpdate
from app.errors import ConflictError, NotFoundError


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[CategoryDTO]:
        rows = await self.session.scalars(select(Category).order_by(Category.id))
        return [CategoryDTO.model_validate(row) for row in rows]

    async def _get_or_raise(self, category_id: int) -> Category:
        category = await self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"category {category_id} not found")
        return category

    async def get(self, category_id: int) -> CategoryDTO:
        return CategoryDTO.model_validate(await self._get_or_raise(category_id))

    async def _ensure_name_free(self, name: str, exclude_id: int | None = None) -> None:
        query = select(Category.id).where(Category.name == name)
        if exclude_id is not None:
            query = query.where(Category.id != exclude_id)
        if await self.session.scalar(query) is not None:
            raise ConflictError(f"category with name {name!r} already exists")

    async def create(self, payload: CategoryCreate) -> CategoryDTO:
        await self._ensure_name_free(payload.name)
        category = Category(**payload.model_dump())
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return CategoryDTO.model_validate(category)

    async def update(self, category_id: int, payload: CategoryUpdate) -> CategoryDTO:
        category = await self._get_or_raise(category_id)
        changes = payload.model_dump(exclude_unset=True)
        if "name" in changes:
            await self._ensure_name_free(changes["name"], exclude_id=category_id)
        for field, value in changes.items():
            setattr(category, field, value)
        await self.session.commit()
        await self.session.refresh(category)
        return CategoryDTO.model_validate(category)

    async def delete(self, category_id: int) -> None:
        category = await self._get_or_raise(category_id)
        await self.session.delete(category)
        await self.session.commit()
