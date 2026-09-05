from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito.base import AvitoClient, ParserResult
from app.db.models import Category, Listing, Seller
from app.domain.schemas import CategoryDTO, ListingDTO, ParserRunResult, SellerRead
from app.errors import NotFoundError


class ParserService:
    def __init__(self, session: AsyncSession, client: AvitoClient) -> None:
        self.session = session
        self.client = client

    async def run(self, category_id: int) -> ParserRunResult:
        category = await self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"category {category_id} not found")

        results = await self.client.parse_category(CategoryDTO.model_validate(category))
        stats = ParserRunResult(category_id=category_id, sellers_matched=len(results))

        for result in results:
            if result.seller.listings_count < category.min_listings_per_seller:
                continue
            seller, created = await self._upsert_seller(category, result)
            if created:
                stats.sellers_created += 1
            else:
                stats.sellers_updated += 1
            for listing in result.listings:
                if await self._upsert_listing(category, seller, listing):
                    stats.listings_created += 1
                else:
                    stats.listings_updated += 1

        await self.session.commit()
        return stats

    async def list_sellers(self, category_id: int | None = None) -> list[SellerRead]:
        query = select(Seller).order_by(Seller.listings_count.desc(), Seller.id)
        if category_id is not None:
            query = query.where(Seller.category_id == category_id)
        rows = await self.session.scalars(query)
        return [SellerRead.model_validate(row) for row in rows]

    async def _upsert_seller(self, category: Category, result: ParserResult) -> tuple[Seller, bool]:
        payload = result.seller
        seller = await self.session.scalar(
            select(Seller).where(Seller.avito_seller_id == payload.avito_seller_id)
        )
        if seller is None:
            seller = Seller(
                avito_seller_id=payload.avito_seller_id,
                name=payload.name,
                profile_url=payload.profile_url,
                listings_count=payload.listings_count,
                region=payload.region,
                category_id=category.id,
            )
            self.session.add(seller)
            await self.session.flush()
            return seller, True

        seller.name = payload.name
        seller.profile_url = payload.profile_url
        seller.listings_count = payload.listings_count
        seller.region = payload.region
        seller.category_id = category.id
        await self.session.flush()
        return seller, False

    async def _upsert_listing(
        self, category: Category, seller: Seller, payload: ListingDTO
    ) -> bool:
        listing = await self.session.scalar(
            select(Listing).where(Listing.avito_listing_id == payload.avito_listing_id)
        )
        if listing is None:
            self.session.add(
                Listing(
                    seller_id=seller.id,
                    avito_listing_id=payload.avito_listing_id,
                    title=payload.title,
                    url=payload.url,
                    category_id=category.id,
                    region=payload.region,
                    price=payload.price,
                )
            )
            await self.session.flush()
            return True

        listing.seller_id = seller.id
        listing.title = payload.title
        listing.url = payload.url
        listing.category_id = category.id
        listing.region = payload.region
        listing.price = payload.price
        await self.session.flush()
        return False
