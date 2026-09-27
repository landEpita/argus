"""
Per-provider cooldowns (a small circuit breaker).

When a provider says "come back in N seconds" (HTTP 429 with a retry hint),
the registry stops calling it until then, instead of spending a request —
and often more quota — every refresh. Repeated failures without a hint open
the circuit for a short, growing delay.
"""

from __future__ import annotations

from dataclasses import dataclass

from argus.infra.clock import Clock, MonotonicClock
from argus.providers.errors import ProviderError, ProviderNotFoundError, ProviderRateLimitedError

FAILURES_BEFORE_OPEN = 5
BASE_DELAY_S = 30.0
MAX_DELAY_S = 15 * 60.0
MAX_HINT_S = 24 * 3600.0


@dataclass(slots=True)
class _State:
    until: float = 0.0
    failures: int = 0
    reason: str = ""


class Cooldowns:
    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or MonotonicClock()
        self._states: dict[str, _State] = {}

    def remaining(self, provider: str) -> float:
        state = self._states.get(provider)
        return 0.0 if state is None else max(0.0, state.until - self._clock.now())

    def reason(self, provider: str) -> str:
        state = self._states.get(provider)
        return state.reason if state else ""

    def record_success(self, provider: str) -> None:
        self._states.pop(provider, None)

    def record_failure(self, provider: str, error: ProviderError) -> None:
        if isinstance(error, ProviderNotFoundError):
            return  # "no such thing" is an answer, not a sign the provider is struggling
        state = self._states.setdefault(provider, _State())
        state.failures += 1
        state.reason = str(error)
        if isinstance(error, ProviderRateLimitedError) and error.retry_after_s:
            delay = min(error.retry_after_s, MAX_HINT_S)
        elif state.failures >= FAILURES_BEFORE_OPEN:
            exponent = state.failures - FAILURES_BEFORE_OPEN
            delay = min(BASE_DELAY_S * 2**exponent, MAX_DELAY_S)
        else:
            return
        state.until = self._clock.now() + delay
