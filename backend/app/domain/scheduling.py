from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

DEFAULT_WINDOW_START = 9
DEFAULT_WINDOW_END = 21
DEFAULT_WEEKDAYS: tuple[int, ...] = (0, 1, 2, 3, 4)

MIN_HOUR = 0
MAX_HOUR = 24
LOOKAHEAD_DAYS = 8

WEEKDAY_NAMES = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


@dataclass(frozen=True)
class ScheduleWindow:
    start_hour: int = DEFAULT_WINDOW_START
    end_hour: int = DEFAULT_WINDOW_END
    weekdays: tuple[int, ...] = DEFAULT_WEEKDAYS
    paused: bool = False


def clamp_window(
    start_hour: int,
    end_hour: int,
    weekdays: list[int] | tuple[int, ...] | None,
    paused: bool = False,
) -> ScheduleWindow:
    start = max(MIN_HOUR, min(start_hour, MAX_HOUR - 1))
    end = max(MIN_HOUR + 1, min(end_hour, MAX_HOUR))
    if end <= start:
        end = start + 1

    days = tuple(sorted({day for day in (weekdays or ()) if 0 <= day <= 6}))
    return ScheduleWindow(start_hour=start, end_hour=end, weekdays=days, paused=paused)


def is_open(window: ScheduleWindow, moment: datetime, tz: tzinfo) -> bool:
    if window.paused or not window.weekdays:
        return False
    local = moment.astimezone(tz)
    if local.weekday() not in window.weekdays:
        return False
    return window.start_hour <= local.hour < window.end_hour


def next_open_at(window: ScheduleWindow, moment: datetime, tz: tzinfo) -> datetime | None:
    if window.paused or not window.weekdays:
        return None
    if is_open(window, moment, tz):
        return moment

    local = moment.astimezone(tz)
    for offset in range(LOOKAHEAD_DAYS):
        day = (local + timedelta(days=offset)).replace(
            hour=window.start_hour, minute=0, second=0, microsecond=0
        )
        if day.weekday() in window.weekdays and day > local:
            return day
    return None


def closed_reason(window: ScheduleWindow, moment: datetime, tz: tzinfo) -> str | None:
    if window.paused:
        return "Бот на паузе — выключен в панели"
    if not window.weekdays:
        return "В расписании не включён ни один день недели"
    local = moment.astimezone(tz)
    if local.weekday() not in window.weekdays:
        return f"Сегодня выходной по расписанию ({WEEKDAY_NAMES[local.weekday()]})"
    if not window.start_hour <= local.hour < window.end_hour:
        return (
            f"Сейчас вне окна отправки {window.start_hour}–{window.end_hour} "
            f"(местное время {local.hour}:00)"
        )
    return None
