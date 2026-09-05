import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito.base import ParserResult
from app.db.base import Base, engine, session_factory
from app.db.models import (
    Account,
    AccountStatus,
    AppSettings,
    Category,
    ScheduleSettings,
    Script,
)
from app.domain.schemas import CategoryCreate, ListingDTO, SellerDTO

SEED_CATEGORIES: list[CategoryCreate] = [
    CategoryCreate(
        name="Бани",
        avito_url_or_slug=(
            "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/banya-ASgBAgICAkRYlrI68I4O2o_OAQ"
        ),
        region="Россия",
        min_listings_per_seller=3,
    ),
    CategoryCreate(
        name="Модульные дома",
        avito_url_or_slug=(
            "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/dom-ASgBAgICAkRYlrI68I4O2I_OAQ"
            "?q=%D0%BC%D0%BE%D0%B4%D1%83%D0%BB%D1%8C%D0%BD%D1%8B%D0%B9+%D0%B4%D0%BE%D0%BC"
        ),
        region="Россия",
        min_listings_per_seller=3,
    ),
    CategoryCreate(
        name="Услуги строительства",
        avito_url_or_slug="all/predlozheniya_uslug/stroitelstvo-ASgBAgICAUSYC6Cf8QI",
        region="Россия",
        min_listings_per_seller=3,
        enabled=False,
    ),
]

SEED_SCRIPTS: list[tuple[int, int, str]] = [
    (
        1,
        1,
        "Здравствуйте, {name}! Смотрю ваши объявления в «{category}». {product} ещё в наличии?",
    ),
    (
        1,
        2,
        "Добрый день, {name}. Заинтересовало «{product}» в категории «{category}». Актуально?",
    ),
    (
        1,
        3,
        "{name}, здравствуйте! Подскажите по позиции «{product}» — берёте сейчас новые заказы?",
    ),
    (
        1,
        4,
        "Здравствуйте! Увидел профиль по теме «{category}». {product} — расскажете подробнее?",
    ),
    (
        1,
        5,
        "{name}, добрый день. Ищу подрядчика по «{category}». Ваш «{product}» доступен?",
    ),
    (
        2,
        1,
        "{name}, добрый день. Писал вам по «{product}». Готов обсудить объём, если вам удобно.",
    ),
    (
        2,
        2,
        "Здравствуйте, {name}! Снова по «{product}». Есть свободные слоты в графике?",
    ),
    (
        2,
        3,
        "{name}, уточню по «{category}»: интересует регулярный поток заказов. Обсудим?",
    ),
    (
        2,
        4,
        "Добрый день. По позиции «{product}» — подскажите сроки и условия работы.",
    ),
    (
        2,
        5,
        "{name}, здравствуйте. Предлагаю сотрудничество по «{category}». Удобно обсудить?",
    ),
    (
        3,
        1,
        "{name}, финально по «{product}»: есть заявки в вашем регионе. Передать контакты?",
    ),
    (
        3,
        2,
        "Здравствуйте, {name}. Готовы направлять вам клиентов по «{category}». Интересно?",
    ),
    (
        3,
        3,
        "{name}, последнее сообщение по теме «{product}». Если актуально, отвечу на вопросы.",
    ),
    (
        3,
        4,
        "Добрый день. Предлагаю партнёрство по «{category}» с оплатой за результат. Обсудим?",
    ),
    (
        3,
        5,
        "{name}, есть заказы по «{product}». Скажите, берёте в работу — и я вышлю условия.",
    ),
]

SEED_ACCOUNT_LOGIN = "demo-operator"
SEED_ACCOUNT_STORAGE_PATH = "data/sessions/demo-operator.storage.json"

SEED_PARSER_RESULTS: list[ParserResult] = [
    ParserResult(
        seller=SellerDTO(
            avito_seller_id="seed-seller-1",
            name="Артём",
            profile_url="https://www.avito.ru/user/seed-seller-1/profile",
            listings_count=4,
            region="Москва",
        ),
        listings=[
            ListingDTO(
                avito_listing_id="seed-listing-1",
                title="Баня-бочка под ключ 4 м",
                url="https://www.avito.ru/moskva/predlozheniya_uslug/seed-listing-1",
                region="Москва",
                price=320000,
            ),
            ListingDTO(
                avito_listing_id="seed-listing-2",
                title="Каркасная баня 3x5",
                url="https://www.avito.ru/moskva/predlozheniya_uslug/seed-listing-2",
                region="Москва",
                price=480000,
            ),
        ],
    ),
    ParserResult(
        seller=SellerDTO(
            avito_seller_id="seed-seller-2",
            name="Ольга",
            profile_url="https://www.avito.ru/user/seed-seller-2/profile",
            listings_count=6,
            region="Казань",
        ),
        listings=[
            ListingDTO(
                avito_listing_id="seed-listing-3",
                title="Модульный дом 36 м2",
                url="https://www.avito.ru/kazan/doma_dachi_kottedzhi/seed-listing-3",
                region="Казань",
                price=1250000,
            ),
        ],
    ),
    ParserResult(
        seller=SellerDTO(
            avito_seller_id="seed-seller-3",
            name="Игорь",
            profile_url="https://www.avito.ru/user/seed-seller-3/profile",
            listings_count=1,
            region="Пермь",
        ),
        listings=[
            ListingDTO(
                avito_listing_id="seed-listing-4",
                title="Печь для бани на заказ",
                url="https://www.avito.ru/perm/predlozheniya_uslug/seed-listing-4",
                region="Пермь",
                price=None,
            ),
        ],
    ),
]


async def seed_categories(session: AsyncSession) -> None:
    for payload in SEED_CATEGORIES:
        existing = await session.scalar(select(Category).where(Category.name == payload.name))
        if existing is None:
            session.add(Category(**payload.model_dump()))


async def seed_scripts(session: AsyncSession) -> None:
    for stage, variant_index, template_text in SEED_SCRIPTS:
        existing = await session.scalar(
            select(Script).where(Script.stage == stage, Script.variant_index == variant_index)
        )
        if existing is None:
            session.add(
                Script(
                    stage=stage,
                    variant_index=variant_index,
                    template_text=template_text,
                    active=True,
                )
            )


async def seed_account(session: AsyncSession) -> None:
    existing = await session.scalar(select(Account).where(Account.login == SEED_ACCOUNT_LOGIN))
    if existing is None:
        session.add(
            Account(
                login=SEED_ACCOUNT_LOGIN,
                session_storage_path=SEED_ACCOUNT_STORAGE_PATH,
                status=AccountStatus.ACTIVE,
                daily_message_count=0,
                daily_limit=15,
                last_reset_at=datetime.now(UTC),
            )
        )


async def seed_settings(session: AsyncSession) -> None:
    if await session.scalar(select(ScheduleSettings).limit(1)) is None:
        session.add(ScheduleSettings())
    if await session.scalar(select(AppSettings).limit(1)) is None:
        session.add(AppSettings())


async def seed_all(session: AsyncSession) -> None:
    await seed_categories(session)
    await seed_scripts(session)
    await seed_account(session)
    await seed_settings(session)
    await session.commit()


async def main() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await seed_all(session)


if __name__ == "__main__":
    asyncio.run(main())
