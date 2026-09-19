"""Rich, believable demo data for the showcase build.

Populates a full working world — accounts in rotation, parsed sellers across
every pipeline stage, real-looking Avito links, sent messages, analysed replies
and delivered leads — so the panel demonstrates end to end on fake clients,
without a single real credential. Idempotent: skips if sellers already exist.
"""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.avito.base import IncomingReplyDTO, ParserResult
from app.db.base import Base, engine, session_factory
from app.db.models import (
    Account,
    AccountStatus,
    BlockKind,
    Category,
    Lead,
    Listing,
    MessageLog,
    MessageStatus,
    Reply,
    Seller,
    SellerStatus,
    Sentiment,
)
from app.db.seed import seed_scripts, seed_settings
from app.domain.schemas import ListingDTO, SellerDTO

AVITO = "https://www.avito.ru"


def _hex(seed: str) -> str:
    return hashlib.md5(seed.encode("utf-8")).hexdigest()


def _profile(seed: str, company: bool) -> str:
    key = _hex(seed)
    return f"{AVITO}/brands/{key}" if company else f"{AVITO}/user/{key}/profile"


# categories: real avito rubric slugs where possible
DEMO_CATEGORIES = [
    ("Бани и сауны", "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/banya", "Россия", True),
    (
        "Модульные дома",
        "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/dom?q=модульный+дом",
        "Россия",
        True,
    ),
    (
        "Каркасные дома",
        "all/remont_i_stroitelstvo/gotovye_stroeniya_i_sruby/dom?q=каркасный+дом",
        "Россия",
        True,
    ),
    ("Беседки", "all/predlozheniya_uslug/stroitelstvo?q=беседка", "Россия", True),
    ("Печи и камины", "all/remont_i_stroitelstvo/pechi_i_kaminy", "Россия", True),
    ("Услуги строительства", "all/predlozheniya_uslug/stroitelstvo", "Москва", False),
]

DEMO_ACCOUNTS = [
    {
        "login": "+7 917 452-88-10",
        "status": AccountStatus.ACTIVE,
        "daily_message_count": 12,
        "proxy_url": "http://usr_msk1:sticky-RU-Moscow-10080@mob.lteboost.com:3021",
    },
    {
        "login": "+7 926 331-07-64",
        "status": AccountStatus.ACTIVE,
        "daily_message_count": 8,
        "proxy_url": "http://usr_msk2:sticky-RU-Kazan-10080@mob.lteboost.com:3022",
    },
    {
        "login": "banya.optom.2024",
        "status": AccountStatus.PAUSED,
        "daily_message_count": 15,
        "proxy_url": "http://usr_spb1:sticky-RU-SPb-10080@mob.lteboost.com:3023",
        "block": BlockKind.RATE_LIMITED,
    },
]

# (name, company, city, listings_count, category_index, status,
#  [(title, url, price)])
DEMO_SELLERS: list[
    tuple[str, bool, str, int, int, SellerStatus, list[tuple[str, str, int | None]]]
] = [
    (
        '"Русская баня"',
        True,
        "Москва",
        11,
        0,
        SellerStatus.LEAD,
        [
            (
                "Перевозная мобильная баня 5,9х4,8 м под ключ",
                f"{AVITO}/moskva/predlozheniya_uslug/perevoznaya_mobilnaya_banya_59h48_m_7816571444",
                641000,
            ),
            (
                "Каркасная баня 3х5 под ключ",
                f"{AVITO}/moskva/predlozheniya_uslug/karkasnaya_banya_3h5_7519930022",
                480000,
            ),
        ],
    ),
    (
        "СтройБаня 24",
        True,
        "Суздаль",
        7,
        0,
        SellerStatus.INTERESTED,
        [
            (
                "Баня под ключ из бруса",
                f"{AVITO}/suzdal/predlozheniya_uslug/banya_pod_klyuch_7957158594",
                390000,
            )
        ],
    ),
    (
        "Игорь",
        False,
        "Киржач",
        5,
        0,
        SellerStatus.INTERESTED,
        [
            (
                "Баня под ключ 6х4",
                f"{AVITO}/kirzhach/predlozheniya_uslug/banya_pod_klyuch_7925779745",
                355000,
            )
        ],
    ),
    (
        "Артём Ковалёв",
        False,
        "Ковров",
        4,
        0,
        SellerStatus.CONTACTED,
        [
            (
                "Мобильная баня 4 м",
                f"{AVITO}/kovrov/predlozheniya_uslug/banya_pod_klyuch_7925738828",
                298000,
            )
        ],
    ),
    (
        "Сергей",
        False,
        "Кольчугино",
        6,
        0,
        SellerStatus.CONTACTED,
        [
            (
                "Баня-бочка 3 м под ключ",
                f"{AVITO}/kolchugino/predlozheniya_uslug/banya_pod_klyuch_7925493007",
                210000,
            )
        ],
    ),
    (
        "БаняПром",
        True,
        "Новокузнецк",
        9,
        0,
        SellerStatus.LEAD,
        [
            (
                "Строительство бань под ключ",
                f"{AVITO}/novokuznetsk/predlozheniya_uslug/stroitelstvo_ban_pod_klyuch_4498822751",
                470000,
            )
        ],
    ),
    (
        "Дом-Модуль",
        True,
        "Казань",
        8,
        1,
        SellerStatus.INTERESTED,
        [
            (
                "Модульный дом 36 м² с отделкой",
                f"{AVITO}/kazan/doma_dachi_kottedzhi/modulnyy_dom_36m_5391372044",
                1250000,
            ),
            (
                "Модульный дом 20 м² дачный",
                f"{AVITO}/kazan/doma_dachi_kottedzhi/modulnyy_dom_20m_5391372099",
                690000,
            ),
        ],
    ),
    (
        "Ольга Мельникова",
        False,
        "Нижний Новгород",
        3,
        1,
        SellerStatus.CONTACTED,
        [
            (
                "Дом-бытовка 6х3 утеплённая",
                f"{AVITO}/nizhniy_novgorod/doma_dachi_kottedzhi/dom_bytovka_6h3_4471120931",
                320000,
            )
        ],
    ),
    (
        "МодульСтрой НН",
        True,
        "Нижний Новгород",
        12,
        1,
        SellerStatus.LEAD,
        [
            (
                "Модульный дом 48 м² под ключ",
                f"{AVITO}/nizhniy_novgorod/doma_dachi_kottedzhi/modulnyy_dom_48m_5120044781",
                1780000,
            )
        ],
    ),
    (
        "Дмитрий",
        False,
        "Пермь",
        4,
        1,
        SellerStatus.REJECTED,
        [
            (
                "Модульный дом на заказ",
                f"{AVITO}/perm/doma_dachi_kottedzhi/modulnyy_dom_na_zakaz_4980221073",
                None,
            )
        ],
    ),
    (
        "КаркасДом Групп",
        True,
        "Екатеринбург",
        14,
        2,
        SellerStatus.INTERESTED,
        [
            (
                "Каркасный дом 8х8 под ключ",
                f"{AVITO}/ekaterinburg/doma_dachi_kottedzhi/karkasnyy_dom_8h8_5233981204",
                2450000,
            ),
            (
                "Каркасный дом 6х6 дачный",
                f"{AVITO}/ekaterinburg/doma_dachi_kottedzhi/karkasnyy_dom_6h6_5233981288",
                1390000,
            ),
        ],
    ),
    (
        "Роман Ефимов",
        False,
        "Челябинск",
        5,
        2,
        SellerStatus.CONTACTED,
        [
            (
                "Каркасный дом 7х9 два этажа",
                f"{AVITO}/chelyabinsk/doma_dachi_kottedzhi/karkasnyy_dom_7h9_5011238470",
                2890000,
            )
        ],
    ),
    (
        "Алексей",
        False,
        "Тюмень",
        3,
        2,
        SellerStatus.NEW,
        [
            (
                "Каркасный дом под ключ",
                f"{AVITO}/tyumen/doma_dachi_kottedzhi/karkasnyy_dom_pod_klyuch_5390012741",
                1990000,
            )
        ],
    ),
    (
        "СтройКаркас",
        True,
        "Уфа",
        8,
        2,
        SellerStatus.CONTACTED,
        [
            (
                "Каркасный дом 9х9 с террасой",
                f"{AVITO}/ufa/doma_dachi_kottedzhi/karkasnyy_dom_9h9_5188230914",
                3150000,
            )
        ],
    ),
    (
        "Беседки56",
        True,
        "Оренбург",
        6,
        3,
        SellerStatus.INTERESTED,
        [
            (
                "Беседка 4х3 с мангальной зоной",
                f"{AVITO}/orenburg/predlozheniya_uslug/besedka_4h3_5771230088",
                175000,
            )
        ],
    ),
    (
        "Виктор",
        False,
        "Самара",
        4,
        3,
        SellerStatus.CONTACTED,
        [
            (
                "Беседка шестигранная под ключ",
                f"{AVITO}/samara/predlozheniya_uslug/besedka_shestigrannaya_4890210773",
                210000,
            )
        ],
    ),
    (
        "Павел Соколов",
        False,
        "Саратов",
        3,
        3,
        SellerStatus.NEW,
        [
            (
                "Беседка деревянная 3х4",
                f"{AVITO}/saratov/predlozheniya_uslug/besedka_derevyannaya_3h4_5012388401",
                98000,
            )
        ],
    ),
    (
        "ПечникЪ",
        True,
        "Ярославль",
        10,
        4,
        SellerStatus.LEAD,
        [
            (
                "Печь для бани с баком под ключ",
                f"{AVITO}/yaroslavl/remont_i_stroitelstvo/pech_dlya_bani_4120983377",
                85000,
            ),
            (
                "Кирпичная банная печь",
                f"{AVITO}/yaroslavl/remont_i_stroitelstvo/kirpichnaya_pech_4120983401",
                140000,
            ),
        ],
    ),
    (
        "Николай",
        False,
        "Владимир",
        5,
        4,
        SellerStatus.CONTACTED,
        [
            (
                "Печь-камин для дома",
                f"{AVITO}/vladimir/remont_i_stroitelstvo/pech_kamin_dlya_doma_4880123094",
                62000,
            )
        ],
    ),
    (
        "КаминДизайн",
        True,
        "Тула",
        7,
        4,
        SellerStatus.INTERESTED,
        [
            (
                "Камин облицовочный под ключ",
                f"{AVITO}/tula/remont_i_stroitelstvo/kamin_oblitsovochnyy_5001238877",
                230000,
            )
        ],
    ),
    (
        "Евгений",
        False,
        "Рязань",
        3,
        4,
        SellerStatus.REJECTED,
        [
            (
                "Установка банной печи",
                f"{AVITO}/ryazan/predlozheniya_uslug/ustanovka_bannoy_pechi_4771029388",
                25000,
            )
        ],
    ),
    (
        "Максим",
        False,
        "Тверь",
        4,
        0,
        SellerStatus.NEW,
        [
            (
                "Баня 3х4 из профилированного бруса",
                f"{AVITO}/tver/predlozheniya_uslug/banya_3h4_brus_7990120044",
                340000,
            )
        ],
    ),
    (
        "СрубМастер",
        True,
        "Кострома",
        13,
        0,
        SellerStatus.CONTACTED,
        [
            (
                "Рубленая баня 5х5 под ключ",
                f"{AVITO}/kostroma/predlozheniya_uslug/rublenaya_banya_5h5_7810234901",
                720000,
            )
        ],
    ),
    (
        "Андрей Гущин",
        False,
        "Иваново",
        6,
        1,
        SellerStatus.INTERESTED,
        [
            (
                "Модульный дом-баня 6х6",
                f"{AVITO}/ivanovo/doma_dachi_kottedzhi/modulnyy_dom_banya_6h6_5120983774",
                1450000,
            )
        ],
    ),
]

REPLY_TEXT = {
    SellerStatus.INTERESTED: "Да, актуально. Расскажите подробнее по условиям и срокам?",
    SellerStatus.LEAD: "Интересно, давайте обсудим. Какой объём заказов и по какой цене?",
    SellerStatus.REJECTED: "Нет, спасибо, работаем только напрямую. Не пишите больше.",
}
REPLY_SENTIMENT = {
    SellerStatus.INTERESTED: (Sentiment.INTERESTED, 0.82),
    SellerStatus.LEAD: (Sentiment.INTERESTED, 0.91),
    SellerStatus.REJECTED: (Sentiment.NEGATIVE, 0.88),
}
# how far each status has walked through the three outreach stages
STAGE_REACHED = {
    SellerStatus.NEW: 0,
    SellerStatus.CONTACTED: 1,
    SellerStatus.INTERESTED: 2,
    SellerStatus.REJECTED: 2,
    SellerStatus.LEAD: 3,
}
STAGE_TEMPLATE = {
    1: "Здравствуйте, {name}! Смотрю ваши объявления в «{category}». «{product}» ещё в наличии?",
    2: "{name}, добрый день. Писал вам по «{product}». Готов обсудить объём, если удобно.",
    3: "{name}, есть заявки в вашем регионе по «{category}». Передать контакты?",
}


def _render(template: str, name: str, product: str, category: str) -> str:
    short_name = name.strip('"').split()[0]
    return template.format(name=short_name, product=product, category=category)


async def _already_seeded(session: AsyncSession) -> bool:
    count = await session.scalar(select(func.count()).select_from(Seller))
    return bool(count)


async def seed_demo(session: AsyncSession) -> None:
    if await _already_seeded(session):
        return

    await seed_scripts(session)
    await seed_settings(session)

    now = datetime.now(UTC)

    categories: list[Category] = []
    for name, slug, region, enabled in DEMO_CATEGORIES:
        category = Category(
            name=name,
            avito_url_or_slug=slug,
            region=region,
            min_listings_per_seller=3,
            enabled=enabled,
        )
        session.add(category)
        categories.append(category)
    await session.flush()

    accounts: list[Account] = []
    for index, spec in enumerate(DEMO_ACCOUNTS):
        paused = spec.get("block") is not None
        account = Account(
            login=str(spec["login"]),
            session_storage_path=f"data/sessions/account-{index + 1}.storage.json",
            status=spec["status"],
            daily_message_count=int(spec["daily_message_count"]),
            daily_limit=15,
            last_reset_at=now.replace(hour=0, minute=1),
            created_at=now - timedelta(days=21 - index * 3),
            proxy_url=str(spec["proxy_url"]),
            paused_until=(now + timedelta(minutes=18)) if paused else None,
            last_block_kind=spec.get("block"),  # type: ignore[arg-type]
            last_block_at=(now - timedelta(minutes=12)) if paused else None,
        )
        session.add(account)
        accounts.append(account)
    await session.flush()

    active_accounts = [a for a in accounts if a.status == AccountStatus.ACTIVE] or accounts

    for index, (name, company, city, listings_count, cat_index, status, listings) in enumerate(
        DEMO_SELLERS
    ):
        category = categories[cat_index]
        contacted_days_ago = index % 9
        seller = Seller(
            avito_seller_id=_hex(f"seller-{index}-{name}"),
            name=name,
            profile_url=_profile(f"seller-{index}-{name}", company),
            listings_count=listings_count,
            region=city,
            category_id=category.id,
            status=status,
            created_at=now - timedelta(days=contacted_days_ago + 2, hours=index % 12),
        )
        session.add(seller)
        await session.flush()

        for l_index, (title, url, price) in enumerate(listings):
            session.add(
                Listing(
                    seller_id=seller.id,
                    avito_listing_id=_hex(f"listing-{index}-{l_index}-{title}"),
                    title=title,
                    url=url,
                    category_id=category.id,
                    region=city,
                    price=price,
                    parsed_at=now - timedelta(days=contacted_days_ago + 2),
                )
            )

        product = listings[0][0]
        stages = STAGE_REACHED[status]
        account = active_accounts[index % len(active_accounts)]
        last_log: MessageLog | None = None

        for stage in range(1, stages + 1):
            # the newest stage of the freshest sellers lands today for a live count
            days_ago = max(0, contacted_days_ago - (stage - 1))
            if index < 3 and stage == stages:
                days_ago = 0
            sent_at = (now - timedelta(days=days_ago, hours=(index + stage) % 10)).replace(
                tzinfo=None
            )
            failed = index == 9 and stage == 2  # one believable failure
            log = MessageLog(
                seller_id=seller.id,
                account_id=account.id,
                stage=stage,
                variant_used=(index + stage) % 5 + 1,
                final_text=_render(STAGE_TEMPLATE[stage], name, product, category.name),
                sent_at=sent_at,
                status=MessageStatus.FAILED if failed else MessageStatus.SENT,
            )
            session.add(log)
            await session.flush()
            last_log = log

        if status in REPLY_TEXT and last_log is not None:
            sentiment, confidence = REPLY_SENTIMENT[status]
            received = (
                now - timedelta(days=max(0, contacted_days_ago - 1), hours=index % 6)
            ).replace(tzinfo=None)
            reply = Reply(
                seller_id=seller.id,
                message_log_id=last_log.id,
                reply_text=REPLY_TEXT[status],
                external_id=_hex(f"reply-{index}"),
                received_at=received,
                ai_sentiment=sentiment,
                ai_confidence=confidence,
                analyzed_at=received + timedelta(seconds=6),
            )
            session.add(reply)
            await session.flush()

            if status == SellerStatus.LEAD:
                history = [
                    {
                        "role": "bot",
                        "text": _render(STAGE_TEMPLATE[1], name, product, category.name),
                        "stage": 1,
                        "sent_at": (received - timedelta(days=2)).isoformat(),
                    },
                    {
                        "role": "seller",
                        "text": REPLY_TEXT[status],
                        "stage": None,
                        "sent_at": received.isoformat(),
                    },
                ]
                session.add(
                    Lead(
                        seller_id=seller.id,
                        reply_id=reply.id,
                        sent_to_telegram_at=received + timedelta(seconds=40),
                        conversation_history=history,
                    )
                )

    await session.commit()


# realistic output for the "Run parser" action while in demo mode
DEMO_PARSER_RESULTS: list[ParserResult] = [
    ParserResult(
        seller=SellerDTO(
            avito_seller_id=_hex('seller-0-"Русская баня"'),
            name='"Русская баня"',
            profile_url=_profile('seller-0-"Русская баня"', True),
            listings_count=11,
            region="Москва",
            status="lead",
        ),
        listings=[
            ListingDTO(
                avito_listing_id=_hex("run-1"),
                title="Перевозная мобильная баня 5,9х4,8 м под ключ",
                url=f"{AVITO}/moskva/predlozheniya_uslug/perevoznaya_mobilnaya_banya_59h48_m_7816571444",
                region="Москва",
                price=641000,
            )
        ],
    ),
    ParserResult(
        seller=SellerDTO(
            avito_seller_id=_hex("run-seller-hutorok"),
            name="Баня-Хуторок",
            profile_url=_profile("run-seller-hutorok", True),
            listings_count=8,
            region="Владимир",
        ),
        listings=[
            ListingDTO(
                avito_listing_id=_hex("run-2"),
                title="Баня из бруса 6х4 под ключ",
                url=f"{AVITO}/vladimir/predlozheniya_uslug/banya_iz_brusa_6h4_7990230118",
                region="Владимир",
                price=430000,
            )
        ],
    ),
    ParserResult(
        seller=SellerDTO(
            avito_seller_id=_hex("run-seller-teremok"),
            name="СрубТеремок",
            profile_url=_profile("run-seller-teremok", True),
            listings_count=6,
            region="Кострома",
        ),
        listings=[
            ListingDTO(
                avito_listing_id=_hex("run-3"),
                title="Рубленая баня 4х4",
                url=f"{AVITO}/kostroma/predlozheniya_uslug/rublenaya_banya_4h4_7810238866",
                region="Кострома",
                price=560000,
            )
        ],
    ),
]

DEMO_INCOMING_REPLIES: list[IncomingReplyDTO] = [
    IncomingReplyDTO(
        external_id=_hex("live-reply-1"),
        avito_seller_id=_hex("seller-3-Артём Ковалёв"),
        text="Да, ещё актуально. По объёму — сколько бань в месяц планируете?",
        received_at=datetime.now(UTC),
        chat_url=f"{AVITO}/profile/messenger/channel/u2i-demo-1",
    ),
    IncomingReplyDTO(
        external_id=_hex("live-reply-2"),
        avito_seller_id=_hex("seller-4-Сергей"),
        text="Интересно, давайте обсудим условия.",
        received_at=datetime.now(UTC),
        chat_url=f"{AVITO}/profile/messenger/channel/u2i-demo-2",
    ),
]


async def main() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        await seed_demo(session)


if __name__ == "__main__":
    asyncio.run(main())
