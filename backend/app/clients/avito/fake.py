from datetime import UTC, datetime

from app.clients.avito.base import AvitoAccountRef, ParserResult, SendResult
from app.db.seed import SEED_PARSER_RESULTS
from app.domain.schemas import CategoryDTO, SellerDTO


class FakeAvitoClient:
    def __init__(
        self,
        results: list[ParserResult] | None = None,
        failure: Exception | None = None,
        fail_times: int = 0,
    ) -> None:
        self.results = results if results is not None else list(SEED_PARSER_RESULTS)
        self.failure = failure
        self.fail_times = fail_times
        self.parsed_categories: list[CategoryDTO] = []
        self.sent: list[tuple[int, str, str]] = []

    def _maybe_fail(self) -> None:
        if self.failure is not None and self.fail_times > 0:
            self.fail_times -= 1
            raise self.failure

    async def parse_category(self, category: CategoryDTO) -> list[ParserResult]:
        validated = CategoryDTO.model_validate(category)
        self.parsed_categories.append(validated)
        self._maybe_fail()
        return [
            result
            for result in self.results
            if result.seller.listings_count >= validated.min_listings_per_seller
        ]

    async def send_message(
        self, account: AvitoAccountRef, seller: SellerDTO, text: str
    ) -> SendResult:
        validated_account = AvitoAccountRef.model_validate(account)
        validated_seller = SellerDTO.model_validate(seller)
        if not text.strip():
            raise ValueError("message text must not be empty")
        try:
            self._maybe_fail()
        except Exception as error:
            return SendResult(status="failed", sent_at=datetime.now(UTC), error=str(error))
        self.sent.append((validated_account.id, validated_seller.avito_seller_id, text))
        return SendResult(status="sent", sent_at=datetime.now(UTC))
