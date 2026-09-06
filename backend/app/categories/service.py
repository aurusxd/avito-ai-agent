from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category, Listing, Seller, SellerStatus
from app.domain.schemas import CategoryCreate, CategoryDTO, CategoryRead, CategoryUpdate
from app.errors import ConflictError, NotFoundError


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_categories(self, region: str | None = None) -> list[CategoryRead]:
        query = select(Category).order_by(Category.id)
        if region is not None:
            query = query.where(Category.region == region)
        rows = list(await self.session.scalars(query))
        return [await self._with_stats(row) for row in rows]

    async def regions(self) -> list[str]:
        rows = await self.session.scalars(
            select(Category.region).distinct().order_by(Category.region)
        )
        return list(rows)

    async def _with_stats(self, category: Category) -> CategoryRead:
        sellers = await self.session.scalar(
            select(func.count()).select_from(Seller).where(Seller.category_id == category.id)
        )
        contacted = await self.session.scalar(
            select(func.count())
            .select_from(Seller)
            .where(
                Seller.category_id == category.id,
                Seller.status != SellerStatus.NEW,
            )
        )
        leads = await self.session.scalar(
            select(func.count())
            .select_from(Seller)
            .where(Seller.category_id == category.id, Seller.status == SellerStatus.LEAD)
        )
        listings = await self.session.scalar(
            select(func.count()).select_from(Listing).where(Listing.category_id == category.id)
        )
        return CategoryRead(
            **CategoryDTO.model_validate(category).model_dump(),
            sellers_found=sellers or 0,
            sellers_contacted=contacted or 0,
            leads=leads or 0,
            listings_found=listings or 0,
        )

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
