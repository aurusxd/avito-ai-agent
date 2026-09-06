from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AppSettings, ScheduleSettings
from app.domain.rotation import clamp_daily_limit, clamp_settings
from app.domain.scheduling import (
    ScheduleWindow,
    clamp_window,
    closed_reason,
    is_open,
    next_open_at,
)
from app.domain.schemas import BotSettingsRead, BotSettingsUpdate


class BotSettingsService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.timezone = ZoneInfo(settings.timezone)

    async def read(self) -> BotSettingsRead:
        schedule = await self._schedule_row()
        limits = await self._limits_row()
        return self._compose(schedule, limits)

    async def update(self, payload: BotSettingsUpdate) -> BotSettingsRead:
        request = BotSettingsUpdate.model_validate(payload)
        schedule = await self._schedule_row()
        limits = await self._limits_row()

        if request.schedule is not None:
            changes = request.schedule.model_dump(exclude_unset=True)
            window = clamp_window(
                changes.get("window_start", schedule.window_start),
                changes.get("window_end", schedule.window_end),
                changes.get("weekdays_enabled", schedule.weekdays_enabled),
                changes.get("paused", schedule.paused),
            )
            schedule.window_start = window.start_hour
            schedule.window_end = window.end_hour
            schedule.weekdays_enabled = list(window.weekdays)
            schedule.paused = window.paused

        if request.limits is not None:
            changes = request.limits.model_dump(exclude_unset=True)
            clamped = clamp_settings(
                changes.get("delay_min_minutes", limits.delay_min_minutes),
                changes.get("delay_max_minutes", limits.delay_max_minutes),
                changes.get("account_rotation_size", limits.account_rotation_size),
            )
            limits.delay_min_minutes = clamped.delay_min_minutes
            limits.delay_max_minutes = clamped.delay_max_minutes
            limits.account_rotation_size = clamped.rotation_size

        await self.session.commit()
        await self.session.refresh(schedule)
        await self.session.refresh(limits)
        return self._compose(schedule, limits)

    async def window(self) -> ScheduleWindow:
        schedule = await self._schedule_row()
        return clamp_window(
            schedule.window_start,
            schedule.window_end,
            schedule.weekdays_enabled,
            schedule.paused,
        )

    def _compose(self, schedule: ScheduleSettings, limits: AppSettings) -> BotSettingsRead:
        now = datetime.now(UTC)
        window = clamp_window(
            schedule.window_start,
            schedule.window_end,
            schedule.weekdays_enabled,
            schedule.paused,
        )
        rotation = clamp_settings(
            limits.delay_min_minutes,
            limits.delay_max_minutes,
            limits.account_rotation_size,
        )
        upcoming = next_open_at(window, now, self.timezone)

        return BotSettingsRead(
            window_start=window.start_hour,
            window_end=window.end_hour,
            weekdays_enabled=list(window.weekdays),
            paused=window.paused,
            delay_min_minutes=rotation.delay_min_minutes,
            delay_max_minutes=rotation.delay_max_minutes,
            account_rotation_size=rotation.rotation_size,
            daily_limit=clamp_daily_limit(self.settings.daily_message_limit),
            timezone=self.settings.timezone,
            window_open_now=is_open(window, now, self.timezone),
            next_window_at=upcoming,
            closed_reason=closed_reason(window, now, self.timezone),
        )

    async def _schedule_row(self) -> ScheduleSettings:
        row = await self.session.scalar(
            select(ScheduleSettings).order_by(ScheduleSettings.id).limit(1)
        )
        if row is None:
            row = ScheduleSettings()
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return row

    async def _limits_row(self) -> AppSettings:
        row = await self.session.scalar(select(AppSettings).order_by(AppSettings.id).limit(1))
        if row is None:
            row = AppSettings()
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
        return row
