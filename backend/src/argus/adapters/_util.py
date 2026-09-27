"""Small parsing helpers shared by adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def as_float(value: Any) -> float | None:
    """A finite float, or None. Strings are parsed; bools are not numbers."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def parse_utc(value: Any) -> datetime | None:
    """ISO-8601 -> aware UTC datetime. Naive timestamps are taken as UTC."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
