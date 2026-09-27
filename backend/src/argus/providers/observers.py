"""
Provider observers (Observer pattern).

The registry announces what happens to each upstream call; observers decide
what to do with it. Health tracking and Prometheus metrics are two observers,
so the registry itself stays ignorant of both.
"""

from __future__ import annotations

from typing import Protocol

from argus.infra.health import HealthRegistry
from argus.infra.metrics import Metrics
from argus.providers.errors import ProviderError, ProviderResponseError


class ProviderObserver(Protocol):
    def on_registered(self, provider: str, capability: str) -> None: ...

    def on_success(self, provider: str, capability: str, duration_s: float) -> None: ...

    def on_failure(
        self, provider: str, capability: str, error: ProviderError, duration_s: float
    ) -> None: ...


class HealthObserver:
    def __init__(self, health: HealthRegistry) -> None:
        self._health = health

    def on_registered(self, provider: str, capability: str) -> None:
        self._health.register(provider)

    def on_success(self, provider: str, capability: str, duration_s: float) -> None:
        self._health.record_success(provider)

    def on_failure(
        self, provider: str, capability: str, error: ProviderError, duration_s: float
    ) -> None:
        self._health.record_failure(provider, str(error))


class MetricsObserver:
    def __init__(self, metrics: Metrics) -> None:
        self._metrics = metrics

    def on_registered(self, provider: str, capability: str) -> None:
        # Pre-create the series so dashboards show zero instead of "no data".
        for outcome in ("success", "unavailable", "bad_response"):
            self._metrics.provider_requests.labels(provider, capability, outcome)

    def on_success(self, provider: str, capability: str, duration_s: float) -> None:
        self._metrics.provider_requests.labels(provider, capability, "success").inc()
        self._metrics.provider_latency.labels(provider, capability).observe(duration_s)

    def on_failure(
        self, provider: str, capability: str, error: ProviderError, duration_s: float
    ) -> None:
        outcome = "bad_response" if isinstance(error, ProviderResponseError) else "unavailable"
        self._metrics.provider_requests.labels(provider, capability, outcome).inc()
        self._metrics.provider_latency.labels(provider, capability).observe(duration_s)
