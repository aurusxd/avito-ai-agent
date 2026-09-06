from hypothesis import given
from hypothesis import strategies as st

from app.domain.templates import PLACEHOLDER_PATTERN
from app.domain.variation import check_variation, normalize_variation

FALLBACK = "Здравствуйте, Артём! Ваша баня ещё актуальна?"
MAX_LENGTH = 500

plain_text = st.text(
    alphabet=st.characters(blacklist_characters="{}"),
    min_size=0,
    max_size=120,
)


def test_accepts_a_rewritten_message() -> None:
    result = check_variation("  Артём, здравствуйте! Баня ещё в работе?  ", FALLBACK, MAX_LENGTH)

    assert result.accepted is True
    assert result.text == "Артём, здравствуйте! Баня ещё в работе?"
    assert result.reason is None


def test_strips_wrapping_quotes_from_model_output() -> None:
    result = check_variation('"Артём, баня ещё актуальна?"', FALLBACK, MAX_LENGTH)

    assert result.accepted is True
    assert result.text == "Артём, баня ещё актуальна?"


def test_rejects_empty_output() -> None:
    result = check_variation("   \n  ", FALLBACK, MAX_LENGTH)

    assert result.accepted is False
    assert result.text == FALLBACK
    assert result.reason == "empty"


def test_rejects_unresolved_placeholder() -> None:
    result = check_variation("Здравствуйте, {name}! Баня актуальна?", FALLBACK, MAX_LENGTH)

    assert result.accepted is False
    assert result.text == FALLBACK
    assert result.reason == "unresolved_placeholder"


def test_rejects_output_longer_than_limit() -> None:
    result = check_variation("а" * (MAX_LENGTH + 1), FALLBACK, MAX_LENGTH)

    assert result.accepted is False
    assert result.text == FALLBACK
    assert result.reason == "too_long"


def test_flags_output_identical_to_template() -> None:
    result = check_variation(FALLBACK, FALLBACK, MAX_LENGTH)

    assert result.accepted is True
    assert result.text == FALLBACK
    assert result.reason == "not_rewritten"


def test_collapses_spaces_and_blank_lines() -> None:
    assert normalize_variation("Привет,   Артём!\n\n\n\nКак дела?") == "Привет, Артём!\n\nКак дела?"


@given(raw=plain_text, max_length=st.integers(min_value=1, max_value=200))
def test_result_is_never_empty(raw: str, max_length: int) -> None:
    result = check_variation(raw, FALLBACK, max_length)

    assert result.text.strip()


@given(raw=plain_text, max_length=st.integers(min_value=1, max_value=200))
def test_accepted_output_respects_limit_and_has_no_placeholders(raw: str, max_length: int) -> None:
    result = check_variation(raw, FALLBACK, max_length)

    if result.accepted:
        assert len(result.text) <= max_length
        assert PLACEHOLDER_PATTERN.search(result.text) is None
    else:
        assert result.text == FALLBACK


@given(raw=st.text(min_size=0, max_size=120))
def test_rejected_output_always_falls_back_to_template(raw: str) -> None:
    result = check_variation(raw, FALLBACK, MAX_LENGTH)

    assert result.accepted or result.text == FALLBACK


@given(raw=plain_text)
def test_normalize_is_idempotent(raw: str) -> None:
    once = normalize_variation(raw)

    assert normalize_variation(once) == once
