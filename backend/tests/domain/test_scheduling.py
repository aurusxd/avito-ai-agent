from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from app.domain.scheduling import (
    MAX_HOUR,
    MIN_HOUR,
    ScheduleWindow,
    clamp_window,
    closed_reason,
    is_open,
    next_open_at,
)

MSK = ZoneInfo("Europe/Moscow")

hours = st.integers(min_value=-30, max_value=50)
weekday_lists = st.lists(st.integers(min_value=-3, max_value=10), max_size=12)
aware_datetimes = st.datetimes(
    min_value=datetime(2026, 1, 1),
    max_value=datetime(2027, 1, 1),
    timezones=st.just(UTC),
)


def window(**overrides: object) -> ScheduleWindow:
    base: dict[str, object] = {
        "start_hour": 9,
        "end_hour": 21,
        "weekdays": (0, 1, 2, 3, 4),
        "paused": False,
    }
    base.update(overrides)
    return ScheduleWindow(**base)  # type: ignore[arg-type]


def msk(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, tzinfo=MSK)


def test_weekday_inside_the_window_is_open() -> None:
    assert is_open(window(), msk(2026, 9, 7, 12), MSK) is True


def test_weekday_before_the_window_is_closed() -> None:
    assert is_open(window(), msk(2026, 9, 7, 8), MSK) is False


def test_end_hour_is_exclusive() -> None:
    assert is_open(window(), msk(2026, 9, 7, 20), MSK) is True
    assert is_open(window(), msk(2026, 9, 7, 21), MSK) is False


def test_weekend_is_closed_by_default() -> None:
    assert is_open(window(), msk(2026, 9, 12, 12), MSK) is False
    assert is_open(window(), msk(2026, 9, 13, 12), MSK) is False


def test_paused_window_is_always_closed() -> None:
    assert is_open(window(paused=True), msk(2026, 9, 7, 12), MSK) is False


def test_window_follows_the_given_timezone() -> None:
    moment = datetime(2026, 9, 7, 7, 0, tzinfo=UTC)

    assert is_open(window(), moment, MSK) is True
    assert is_open(window(), moment, UTC) is False


def test_next_open_skips_the_weekend() -> None:
    friday_evening = msk(2026, 9, 11, 22)

    assert next_open_at(window(), friday_evening, MSK) == msk(2026, 9, 14, 9)


def test_next_open_returns_the_same_moment_when_already_open() -> None:
    now = msk(2026, 9, 7, 12)

    assert next_open_at(window(), now, MSK) == now


def test_next_open_is_none_when_paused_or_without_weekdays() -> None:
    now = msk(2026, 9, 7, 12)

    assert next_open_at(window(paused=True), now, MSK) is None
    assert next_open_at(window(weekdays=()), now, MSK) is None


def test_closed_reason_explains_why() -> None:
    assert closed_reason(window(), msk(2026, 9, 7, 12), MSK) is None
    assert "паузе" in (closed_reason(window(paused=True), msk(2026, 9, 7, 12), MSK) or "")
    assert "выходной" in (closed_reason(window(), msk(2026, 9, 12, 12), MSK) or "")
    assert "окна" in (closed_reason(window(), msk(2026, 9, 7, 6), MSK) or "")


@given(start=hours, end=hours, weekdays=weekday_lists, paused=st.booleans())
def test_clamp_always_produces_a_usable_window(
    start: int, end: int, weekdays: list[int], paused: bool
) -> None:
    result = clamp_window(start, end, weekdays, paused)

    assert MIN_HOUR <= result.start_hour < result.end_hour <= MAX_HOUR
    assert all(0 <= day <= 6 for day in result.weekdays)
    assert list(result.weekdays) == sorted(set(result.weekdays))
    assert result.paused is paused


@given(start=hours, end=hours, weekdays=weekday_lists, moment=aware_datetimes)
def test_open_implies_enabled_weekday_and_hour(
    start: int, end: int, weekdays: list[int], moment: datetime
) -> None:
    result = clamp_window(start, end, weekdays)

    if is_open(result, moment, MSK):
        local = moment.astimezone(MSK)
        assert local.weekday() in result.weekdays
        assert result.start_hour <= local.hour < result.end_hour
        assert result.paused is False


@given(start=hours, end=hours, weekdays=weekday_lists, moment=aware_datetimes)
def test_next_open_is_never_in_the_past_and_is_open(
    start: int, end: int, weekdays: list[int], moment: datetime
) -> None:
    result = clamp_window(start, end, weekdays)
    upcoming = next_open_at(result, moment, MSK)

    if upcoming is not None:
        assert upcoming >= moment
        assert is_open(result, upcoming, MSK)


@given(start=hours, end=hours, weekdays=weekday_lists, moment=aware_datetimes)
def test_a_window_with_weekdays_always_reopens(
    start: int, end: int, weekdays: list[int], moment: datetime
) -> None:
    result = clamp_window(start, end, weekdays)

    if result.weekdays:
        assert next_open_at(result, moment, MSK) is not None


@given(start=hours, end=hours, weekdays=weekday_lists, moment=aware_datetimes)
def test_closed_reason_is_present_exactly_when_closed(
    start: int, end: int, weekdays: list[int], moment: datetime
) -> None:
    result = clamp_window(start, end, weekdays)

    assert (closed_reason(result, moment, MSK) is None) == is_open(result, moment, MSK)
