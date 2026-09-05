from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.domain.schemas import MessageDTO, Stage


class LeadNotification(BaseModel):
    seller_name: str = Field(min_length=1)
    listing_url: str = Field(min_length=1)
    conversation_history: list[MessageDTO] = Field(min_length=1)
    stage_reached: Stage


@runtime_checkable
class Notifier(Protocol):
    async def send_lead(self, notification: LeadNotification) -> None: ...
