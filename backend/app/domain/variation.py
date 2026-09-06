import re
from dataclasses import dataclass
from typing import Literal

from app.domain.templates import PLACEHOLDER_PATTERN

VariationSourceLiteral = Literal["ai", "template"]
RejectReason = Literal[
    "empty",
    "unresolved_placeholder",
    "too_long",
    "not_rewritten",
]

WHITESPACE = re.compile(r"[ \t ]+")
BLANK_LINES = re.compile(r"\n{3,}")
WRAPPING_QUOTES = ('"', "'", "«", "»", "`")


@dataclass(frozen=True)
class VariationCheck:
    accepted: bool
    text: str
    reason: str | None = None


def normalize_variation(raw: str) -> str:
    text = raw.strip()
    while text and text[0] in WRAPPING_QUOTES and text[-1] in WRAPPING_QUOTES and len(text) > 1:
        text = text[1:-1].strip()
    text = WHITESPACE.sub(" ", text)
    text = BLANK_LINES.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def check_variation(raw: str, fallback: str, max_length: int) -> VariationCheck:
    candidate = normalize_variation(raw)

    if not candidate:
        return VariationCheck(False, fallback, "empty")
    if PLACEHOLDER_PATTERN.search(candidate):
        return VariationCheck(False, fallback, "unresolved_placeholder")
    if len(candidate) > max_length:
        return VariationCheck(False, fallback, "too_long")
    if candidate == normalize_variation(fallback):
        return VariationCheck(True, candidate, "not_rewritten")

    return VariationCheck(True, candidate)
