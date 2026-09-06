import json
import re
from typing import Literal

SellerStatusLiteral = Literal["new", "contacted", "interested", "lead", "rejected"]
SentimentLiteral = Literal["interested", "neutral", "negative"]

DEFAULT_SENTIMENT_THRESHOLD = 0.6

AUTOMATIC_TERMINAL_STATUSES: frozenset[str] = frozenset({"lead", "rejected"})

SENTIMENT_VALUES: frozenset[str] = frozenset({"interested", "neutral", "negative"})

JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def next_seller_status(
    current: SellerStatusLiteral,
    sentiment: SentimentLiteral,
    confidence: float,
    threshold: float = DEFAULT_SENTIMENT_THRESHOLD,
) -> SellerStatusLiteral:
    if current in AUTOMATIC_TERMINAL_STATUSES:
        return current
    if confidence < threshold:
        return current
    if sentiment == "interested":
        return "interested"
    if sentiment == "negative":
        return "rejected"
    return current


def parse_sentiment_payload(raw: str) -> tuple[SentimentLiteral, float] | None:
    match = JSON_OBJECT.search(raw)
    if match is None:
        return None

    try:
        payload = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    sentiment = payload.get("sentiment")
    if not isinstance(sentiment, str):
        return None
    sentiment = sentiment.strip().lower()
    if sentiment not in SENTIMENT_VALUES:
        return None

    raw_confidence = payload.get("confidence", 0.0)
    if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, int | float):
        return None

    confidence = min(1.0, max(0.0, float(raw_confidence)))
    return sentiment, confidence  # type: ignore[return-value]
