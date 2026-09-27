"""
Passive health registry (idea from Oracle-X).

Nothing here calls a provider. The provider registry reports the outcome of
calls the platform already makes, so the health badge reflects real traffic
and spends no rate limit of its own. A source nobody has called yet is
``idle`` rather than guessed at; one silent for too long is ``stale``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from argus.infra.clock import Clock, MonotonicClock


class HealthStatus(StrEnum):
    OK = "ok"
    FAILING = "failing"
    STALE = "stale"
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class SourceHealth:
    source: str
    status: HealthStatus
    last_success_age_s: float | None
    last_error: str | None
    consecutive_failures: int


@dataclass(slots=True)
class _State:
    last_success: float | None = None
    last_failure: float | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


class HealthRegistry:
    def __init__(self, clock: Clock | None = None, stale_after_s: float = 30 * 60) -> None:
        self._clock = clock or MonotonicClock()
        self._stale_after_s = stale_after_s
        self._states: dict[str, _State] = {}

    def register(self, source: str) -> None:
        self._states.setdefault(source, _State())

    def record_success(self, source: str) -> None:
        state = self._states.setdefault(source, _State())
        state.last_success = self._clock.now()
        state.consecutive_failures = 0

    def record_failure(self, source: str, error: str) -> None:
        state = self._states.setdefault(source, _State())
        state.last_failure = self._clock.now()
        state.last_error = error
        state.consecutive_failures += 1

    def snapshot(self) -> list[SourceHealth]:
        now = self._clock.now()
        return [self._evaluate(name, state, now) for name, state in sorted(self._states.items())]

    def _evaluate(self, name: str, state: _State, now: float) -> SourceHealth:
        age = None if state.last_success is None else now - state.last_success
        if state.consecutive_failures > 0:
            status = HealthStatus.FAILING
        elif age is None:
            status = HealthStatus.IDLE
        elif age > self._stale_after_s:
            status = HealthStatus.STALE
        else:
            status = HealthStatus.OK
        return SourceHealth(
            source=name,
            status=status,
            last_success_age_s=age,
            last_error=state.last_error if status is HealthStatus.FAILING else None,
            consecutive_failures=state.consecutive_failures,
        )
