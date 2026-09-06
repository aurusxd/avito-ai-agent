from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.domain.auth_session import (
    AWAITING_OPERATOR,
    TERMINAL_STATUSES,
    LoginSession,
    LoginStatusLiteral,
    advance,
    awaits_operator,
    can_submit_code,
    expire,
    expires_at,
    is_expired,
    is_terminal,
)

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
TTL = 600

statuses: st.SearchStrategy[LoginStatusLiteral] = st.sampled_from(
    ["starting", "code_required", "captcha_required", "saving", "done", "failed", "expired"]
)
ttls = st.integers(min_value=-100, max_value=3600)
offsets = st.integers(min_value=-3600, max_value=7200)


def session(**overrides: object) -> LoginSession:
    base: dict[str, object] = {
        "session_id": "sess-1",
        "login": "operator-1",
        "status": "starting",
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(overrides)
    return LoginSession(**base)  # type: ignore[arg-type]


def test_flow_walks_from_start_to_done() -> None:
    current = session()
    current = advance(current, "code_required", NOW, hint="введите код из СМС")
    assert can_submit_code(current) is True
    assert awaits_operator(current) is True

    current = advance(current, "saving", NOW)
    assert can_submit_code(current) is False

    current = advance(current, "done", NOW, account_id=7)
    assert is_terminal(current) is True
    assert current.account_id == 7


def test_captcha_waits_for_a_human() -> None:
    current = advance(session(), "captcha_required", NOW, hint="нужен человек", has_screenshot=True)

    assert awaits_operator(current) is True
    assert can_submit_code(current) is False
    assert current.has_screenshot is True


def test_done_session_is_frozen() -> None:
    done = advance(session(), "done", NOW, account_id=3)

    assert advance(done, "code_required", NOW) == done
    assert advance(done, "failed", NOW) == done


def test_failed_session_is_frozen() -> None:
    failed = advance(session(), "failed", NOW, hint="wrong password")

    assert advance(failed, "starting", NOW) == failed


def test_account_id_survives_later_steps() -> None:
    current = advance(session(), "saving", NOW, account_id=5)
    current = advance(current, "done", NOW)

    assert current.account_id == 5


def test_session_expires_after_the_ttl() -> None:
    current = session()

    assert is_expired(current, NOW + timedelta(seconds=TTL - 1), TTL) is False
    assert is_expired(current, NOW + timedelta(seconds=TTL), TTL) is True

    expired = expire(current, NOW + timedelta(seconds=TTL), TTL)
    assert expired.status == "expired"
    assert expired.hint is not None


def test_activity_pushes_the_deadline() -> None:
    current = session()
    later = NOW + timedelta(seconds=300)
    current = advance(current, "code_required", later)

    assert expires_at(current, TTL) == later + timedelta(seconds=TTL)
    assert is_expired(current, later + timedelta(seconds=TTL - 1), TTL) is False


def test_terminal_session_never_expires() -> None:
    done = advance(session(), "done", NOW)

    assert is_expired(done, NOW + timedelta(days=7), TTL) is False
    assert expire(done, NOW + timedelta(days=7), TTL) == done


@given(status=statuses, target=statuses, ttl=ttls)
def test_terminal_status_is_never_left(
    status: LoginStatusLiteral, target: LoginStatusLiteral, ttl: int
) -> None:
    current = session(status=status)
    result = advance(current, target, NOW)

    if status in TERMINAL_STATUSES:
        assert result == current
    else:
        assert result.status == target


@given(status=statuses, offset=offsets, ttl=ttls)
def test_expire_is_idempotent(status: LoginStatusLiteral, offset: int, ttl: int) -> None:
    current = session(status=status)
    moment = NOW + timedelta(seconds=offset)

    once = expire(current, moment, ttl)
    twice = expire(once, moment, ttl)

    assert once == twice


@given(status=statuses, offset=offsets, ttl=ttls)
def test_expired_session_is_terminal(status: LoginStatusLiteral, offset: int, ttl: int) -> None:
    current = expire(session(status=status), NOW + timedelta(seconds=offset), ttl)

    if current.status == "expired":
        assert is_terminal(current)


@given(status=statuses)
def test_only_code_required_accepts_a_code(status: LoginStatusLiteral) -> None:
    current = session(status=status)

    assert can_submit_code(current) == (status == "code_required")
    assert awaits_operator(current) == (status in AWAITING_OPERATOR)


@given(status=statuses, target=statuses)
def test_advance_never_moves_time_backwards(
    status: LoginStatusLiteral, target: LoginStatusLiteral
) -> None:
    current = session(status=status)
    later = NOW + timedelta(seconds=42)

    result = advance(current, target, later)

    assert result.updated_at >= current.updated_at
