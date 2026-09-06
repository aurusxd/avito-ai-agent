from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ai.base import AIClient, AIUnavailableError, AIVariationRequest
from app.config import Settings
from app.db.models import Category, Listing, Script, Seller
from app.domain.schemas import Stage, VariationRequest, VariationResult
from app.domain.templates import render_template
from app.domain.variation import check_variation
from app.errors import NotFoundError

FALLBACK_PRODUCT = "ваше объявление"
FALLBACK_CATEGORY = "категория"


class VariationService:
    def __init__(self, session: AsyncSession, client: AIClient, settings: Settings) -> None:
        self.session = session
        self.client = client
        self.settings = settings

    async def preview(self, request: VariationRequest) -> VariationResult:
        payload = VariationRequest.model_validate(request)

        seller = await self.session.get(Seller, payload.seller_id)
        if seller is None:
            raise NotFoundError(f"seller {payload.seller_id} not found")

        script = await self._pick_script(payload.stage, payload.variant_index)
        if script is None:
            raise NotFoundError(f"no active script for stage {payload.stage}")

        return await self.compose(seller, payload.stage, script)

    async def compose(self, seller: Seller, stage: Stage, script: Script) -> VariationResult:
        product = await self.product_for(seller)
        category = await self.category_name(seller)
        rendered = render_template(
            script.template_text, name=seller.name, product=product, category=category
        )

        result = VariationResult(
            seller_id=seller.id,
            stage=stage,
            variant_used=script.variant_index,
            template_text=rendered,
            final_text=rendered,
            source="template",
        )

        try:
            response = await self.client.rewrite(
                AIVariationRequest(
                    template_text=script.template_text,
                    seller_name=seller.name,
                    product=product,
                    category=category,
                )
            )
        except AIUnavailableError as error:
            logger.warning(
                "ai rewrite unavailable for seller {seller}, sending the template: {reason}",
                seller=seller.id,
                reason=str(error),
            )
            return result.model_copy(update={"reason": str(error)})

        check = check_variation(
            response.unique_text, rendered, self.settings.ai_max_variation_length
        )
        if not check.accepted:
            logger.warning(
                "ai variation rejected for seller {seller}: {reason}",
                seller=seller.id,
                reason=check.reason,
            )

        return result.model_copy(
            update={
                "final_text": check.text,
                "source": "ai" if check.accepted else "template",
                "provider": self._provider_name(),
                "reason": check.reason,
            }
        )

    async def product_for(self, seller: Seller) -> str:
        listing = await self.session.scalar(
            select(Listing).where(Listing.seller_id == seller.id).order_by(Listing.id).limit(1)
        )
        return listing.title if listing else FALLBACK_PRODUCT

    async def category_name(self, seller: Seller) -> str:
        category = await self.session.get(Category, seller.category_id)
        return category.name if category else FALLBACK_CATEGORY

    def _provider_name(self) -> str | None:
        last = getattr(self.client, "last_provider", None)
        return last or getattr(self.client, "provider", None)

    async def _pick_script(self, stage: Stage, variant_index: int | None) -> Script | None:
        query = select(Script).where(Script.stage == stage, Script.active.is_(True))
        if variant_index is not None:
            query = query.where(Script.variant_index == variant_index)
        return await self.session.scalar(query.order_by(Script.variant_index).limit(1))
