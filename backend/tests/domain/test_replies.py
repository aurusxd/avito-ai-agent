from hypothesis import given
from hypothesis import strategies as st

from app.domain.replies import (
    AUTOMATIC_TERMINAL_STATUSES,
    DEFAULT_SENTIMENT_THRESHOLD,
    SellerStatusLiteral,
    SentimentLiteral,
    next_seller_status,
    parse_sentiment_payload,
)

statuses: st.SearchStrategy[SellerStatusLiteral] = st.sampled_from(
    ["new", "contacted", "interested", "lead", "rejected"]
)
sentiments: st.SearchStrategy[SentimentLiteral] = st.sampled_from(
    ["interested", "neutral", "negative"]
)
confidences = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
thresholds = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


def test_confident_interest_moves_a_contacted_seller() -> None:
    assert next_seller_status("contacted", "interested", 0.9) == "interested"


def test_confident_refusal_rejects_a_contacted_seller() -> None:
    assert next_seller_status("contacted", "negative", 0.9) == "rejected"


def test_neutral_reply_changes_nothing() -> None:
    assert next_seller_status("contacted", "neutral", 1.0) == "contacted"


def test_low_confidence_changes_nothing() -> None:
    assert next_seller_status("contacted", "interested", 0.4) == "contacted"
    assert next_seller_status("contacted", "negative", 0.4) == "contacted"


def test_delivered_lead_is_never_downgraded() -> None:
    assert next_seller_status("lead", "negative", 1.0) == "lead"
    assert next_seller_status("lead", "neutral", 1.0) == "lead"


def test_refusal_is_sticky() -> None:
    assert next_seller_status("rejected", "interested", 1.0) == "rejected"


def test_interest_can_still_flip_to_refusal_before_the_lead() -> None:
    assert next_seller_status("interested", "negative", 0.9) == "rejected"


@given(
    current=statuses,
    sentiment=sentiments,
    confidence=confidences,
    threshold=thresholds,
)
def test_terminal_statuses_never_change(
    current: SellerStatusLiteral,
    sentiment: SentimentLiteral,
    confidence: float,
    threshold: float,
) -> None:
    result = next_seller_status(current, sentiment, confidence, threshold)

    if current in AUTOMATIC_TERMINAL_STATUSES:
        assert result == current


@given(
    current=statuses,
    sentiment=sentiments,
    confidence=confidences,
    threshold=thresholds,
)
def test_transition_is_idempotent(
    current: SellerStatusLiteral,
    sentiment: SentimentLiteral,
    confidence: float,
    threshold: float,
) -> None:
    once = next_seller_status(current, sentiment, confidence, threshold)
    twice = next_seller_status(once, sentiment, confidence, threshold)

    assert once == twice


@given(current=statuses, confidence=confidences, threshold=thresholds)
def test_neutral_never_moves_a_seller(
    current: SellerStatusLiteral, confidence: float, threshold: float
) -> None:
    assert next_seller_status(current, "neutral", confidence, threshold) == current


@given(current=statuses, sentiment=sentiments, threshold=st.floats(0.01, 1.0))
def test_below_threshold_never_moves_a_seller(
    current: SellerStatusLiteral, sentiment: SentimentLiteral, threshold: float
) -> None:
    assert next_seller_status(current, sentiment, threshold - 0.01, threshold) == current


@given(current=statuses, sentiment=sentiments, confidence=confidences)
def test_result_is_always_a_known_status(
    current: SellerStatusLiteral, sentiment: SentimentLiteral, confidence: float
) -> None:
    result = next_seller_status(current, sentiment, confidence, DEFAULT_SENTIMENT_THRESHOLD)

    assert result in {"new", "contacted", "interested", "lead", "rejected"}


def test_parses_a_plain_json_answer() -> None:
    assert parse_sentiment_payload('{"sentiment": "interested", "confidence": 0.82}') == (
        "interested",
        0.82,
    )


def test_parses_json_wrapped_in_a_markdown_fence() -> None:
    raw = 'Вот результат:\n```json\n{"sentiment": "negative", "confidence": 0.9}\n```'

    assert parse_sentiment_payload(raw) == ("negative", 0.9)


def test_clamps_confidence_outside_the_range() -> None:
    assert parse_sentiment_payload('{"sentiment": "neutral", "confidence": 7}') == ("neutral", 1.0)
    assert parse_sentiment_payload('{"sentiment": "neutral", "confidence": -3}') == ("neutral", 0.0)


def test_defaults_missing_confidence_to_zero() -> None:
    assert parse_sentiment_payload('{"sentiment": "neutral"}') == ("neutral", 0.0)


def test_rejects_unknown_sentiment() -> None:
    assert parse_sentiment_payload('{"sentiment": "curious", "confidence": 0.9}') is None


def test_rejects_boolean_confidence() -> None:
    assert parse_sentiment_payload('{"sentiment": "neutral", "confidence": true}') is None


def test_rejects_non_json_answer() -> None:
    assert parse_sentiment_payload("продавец, кажется, заинтересован") is None
    assert parse_sentiment_payload("") is None
    assert parse_sentiment_payload("{broken json") is None


@given(raw=st.text(max_size=200))
def test_parsing_never_raises(raw: str) -> None:
    result = parse_sentiment_payload(raw)

    assert result is None or (result[0] in {"interested", "neutral", "negative"})


@given(raw=st.text(max_size=200))
def test_parsed_confidence_stays_in_range(raw: str) -> None:
    result = parse_sentiment_payload(raw)

    if result is not None:
        assert 0.0 <= result[1] <= 1.0
