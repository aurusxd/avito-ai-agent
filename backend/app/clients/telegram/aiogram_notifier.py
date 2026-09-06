import html

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import AiogramError

from app.clients.telegram.base import LeadNotification, NotifierUnavailableError
from app.config import Settings, get_settings

ROLE_LABEL = {"bot": "Мы", "seller": "Продавец"}


def build_lead_message(notification: LeadNotification) -> str:
    lines = [
        "<b>Новый лид с Авито</b>",
        f"Продавец: {html.escape(notification.seller_name)}",
        f"Этап: {notification.stage_reached}",
        f'Объявление: <a href="{html.escape(notification.listing_url)}">ссылка</a>',
        "",
        "<b>Переписка</b>",
    ]
    for message in notification.conversation_history:
        stamp = message.sent_at.strftime("%d.%m %H:%M")
        who = ROLE_LABEL.get(message.role, message.role)
        lines.append(f"<i>{stamp}</i> <b>{who}:</b> {html.escape(message.text)}")
    return "\n".join(lines)


class AiogramNotifier:
    provider = "aiogram"

    def __init__(self, settings: Settings | None = None, bot: Bot | None = None) -> None:
        self.settings = settings or get_settings()
        self._bot = bot

    def _build_bot(self) -> Bot:
        if not self.settings.telegram_bot_token:
            raise NotifierUnavailableError("telegram bot token is not configured", self.provider)
        return Bot(
            token=self.settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

    async def send_lead(self, notification: LeadNotification) -> None:
        validated = LeadNotification.model_validate(notification)

        chat_id = self.settings.telegram_operator_chat_id
        if not chat_id:
            raise NotifierUnavailableError(
                "telegram operator chat is not configured", self.provider
            )

        bot = self._bot or self._build_bot()
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=build_lead_message(validated),
                disable_web_page_preview=True,
            )
        except AiogramError as error:
            raise NotifierUnavailableError(
                f"telegram rejected the lead: {type(error).__name__}", self.provider
            ) from error
        except OSError as error:
            raise NotifierUnavailableError(
                f"telegram is unreachable: {type(error).__name__}", self.provider
            ) from error
        finally:
            if self._bot is None:
                await bot.session.close()
