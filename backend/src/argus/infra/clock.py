"""Injectable clocks, so time-dependent code is testable without sleeping."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Monotonic seconds: for durations and TTLs."""
        ...


class WallClock(Protocol):
    def utcnow(self) -> datetime:
        """Timezone-aware current time: for "events since" windows."""
        ...


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


class SystemWallClock:
    def utcnow(self) -> datetime:
        return datetime.now(UTC)
