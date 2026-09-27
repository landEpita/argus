"""
Capability registry (Strategy + Chain of Responsibility).

Several fetchers may serve one capability. They are tried in priority order;
a :class:`ProviderError` moves on to the next one. Every outcome is announced
to the observers (health, metrics) so the UI and dashboards show what is
degraded.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, cast

from pydantic import BaseModel

from argus.domain.capability import Capability
from argus.infra.clock import Clock, MonotonicClock
from argus.providers.base import Fetcher
from argus.providers.cooldown import Cooldowns
from argus.providers.errors import (
    AllProvidersFailedError,
    NoProviderError,
    ProviderError,
    ProviderUnavailableError,
    UnsupportedQueryError,
)
from argus.providers.observers import ProviderObserver

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(
        self,
        observers: Sequence[ProviderObserver] = (),
        clock: Clock | None = None,
        cooldowns: Cooldowns | None = None,
    ) -> None:
        self._observers = tuple(observers)
        self._clock = clock or MonotonicClock()
        self._cooldowns = cooldowns or Cooldowns(self._clock)
        self._fetchers: dict[Capability[Any, Any], list[tuple[int, Fetcher[Any, Any]]]] = (
            defaultdict(list)
        )

    def register[Q: BaseModel, R](
        self, capability: Capability[Q, R], fetcher: Fetcher[Q, R], *, priority: int = 100
    ) -> None:
        """Register a fetcher. Lower ``priority`` is tried first."""
        entries = self._fetchers[capability]
        entries.append((priority, fetcher))
        entries.sort(key=lambda entry: entry[0])
        for observer in self._observers:
            observer.on_registered(fetcher.provider_name, capability.name)

    def providers_for(self, capability: Capability[Any, Any]) -> list[str]:
        return [f.provider_name for _, f in self._fetchers.get(capability, [])]

    def capabilities(self) -> dict[str, list[str]]:
        return {cap.name: self.providers_for(cap) for cap in self._fetchers}

    async def fetch[Q: BaseModel, R](self, capability: Capability[Q, R], query: Q) -> R:
        entries = self._fetchers.get(capability)
        if not entries:
            raise NoProviderError(capability.name)

        errors: list[ProviderError] = []
        for _, fetcher in entries:
            provider = fetcher.provider_name
            wait = self._cooldowns.remaining(provider)
            if wait > 0:
                # Not called at all: no request spent, no new health or metrics event.
                errors.append(
                    ProviderUnavailableError(
                        provider,
                        f"cooling down for {wait:.0f} s ({self._cooldowns.reason(provider)})",
                    )
                )
                continue
            started = self._clock.now()
            try:
                result = await fetcher.fetch(query)
            except UnsupportedQueryError as exc:
                # Out of this provider's scope, not a fault: no health or metrics impact.
                errors.append(exc)
                continue
            except ProviderError as exc:
                elapsed = self._clock.now() - started
                logger.warning(
                    "provider failed",
                    extra={"provider": provider, "capability": capability.name, "error": str(exc)},
                )
                for observer in self._observers:
                    observer.on_failure(provider, capability.name, exc, elapsed)
                self._cooldowns.record_failure(provider, exc)
                errors.append(exc)
                continue
            elapsed = self._clock.now() - started
            self._cooldowns.record_success(provider)
            for observer in self._observers:
                observer.on_success(provider, capability.name, elapsed)
            return cast("R", result)
        raise AllProvidersFailedError(capability.name, errors)
