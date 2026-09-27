import pytest

from argus.domain.aviation import AIRCRAFT_STATES, Aircraft, AircraftQuery
from argus.infra.health import HealthRegistry, HealthStatus
from argus.providers.cooldown import BASE_DELAY_S, FAILURES_BEFORE_OPEN, MAX_HINT_S, Cooldowns
from argus.providers.errors import (
    AllProvidersFailedError,
    ProviderNotFoundError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from argus.providers.observers import HealthObserver
from argus.providers.registry import ProviderRegistry
from tests.fakes import FakeClock, StubAircraftFetcher, make_aircraft


class TestCooldowns:
    def test_retry_hint_is_honoured_and_capped(self) -> None:
        clock = FakeClock()
        cooldowns = Cooldowns(clock)
        cooldowns.record_failure("opensky", ProviderRateLimitedError("opensky", "HTTP 429", 120))
        assert cooldowns.remaining("opensky") == 120
        assert "429" in cooldowns.reason("opensky")
        clock.advance(120)
        assert cooldowns.remaining("opensky") == 0
        cooldowns.record_failure("opensky", ProviderRateLimitedError("opensky", "x", 10**9))
        assert cooldowns.remaining("opensky") == MAX_HINT_S

    def test_repeated_failures_open_with_growing_delay(self) -> None:
        cooldowns = Cooldowns(FakeClock())
        for _ in range(FAILURES_BEFORE_OPEN - 1):
            cooldowns.record_failure("x", ProviderUnavailableError("x", "timeout"))
        assert cooldowns.remaining("x") == 0
        cooldowns.record_failure("x", ProviderUnavailableError("x", "timeout"))
        assert cooldowns.remaining("x") == BASE_DELAY_S
        cooldowns.record_failure("x", ProviderUnavailableError("x", "timeout"))
        assert cooldowns.remaining("x") == 2 * BASE_DELAY_S

    def test_success_and_not_found_do_not_open(self) -> None:
        cooldowns = Cooldowns(FakeClock())
        for _ in range(10):
            cooldowns.record_failure("x", ProviderNotFoundError("x", "HTTP 404"))
        assert cooldowns.remaining("x") == 0
        cooldowns.record_failure("x", ProviderRateLimitedError("x", "429", 60))
        cooldowns.record_success("x")
        assert cooldowns.remaining("x") == 0
        assert cooldowns.reason("x") == ""


async def test_registry_skips_a_cooling_provider_without_calling_it() -> None:
    clock = FakeClock()
    health = HealthRegistry(clock=clock)
    calls: list[str] = []

    def limited(_: AircraftQuery) -> list[Aircraft]:
        calls.append("opensky")
        raise ProviderRateLimitedError("opensky", "HTTP 429", 3600)

    def backup(_: AircraftQuery) -> list[Aircraft]:
        calls.append("adsblol")
        return [make_aircraft(source="adsblol")]

    registry = ProviderRegistry([HealthObserver(health)], clock=clock)
    registry.register(AIRCRAFT_STATES, StubAircraftFetcher(limited, name="opensky"), priority=1)
    registry.register(AIRCRAFT_STATES, StubAircraftFetcher(backup, name="adsblol"), priority=2)

    for _ in range(3):
        await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert calls == ["opensky", "adsblol", "adsblol", "adsblol"]
    assert {s.source: s.status for s in health.snapshot()}["opensky"] is HealthStatus.FAILING

    clock.advance(3600)
    await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert calls[-2:] == ["opensky", "adsblol"]


async def test_cooling_down_is_reported_when_nothing_else_can_answer() -> None:
    def limited(_: AircraftQuery) -> list[Aircraft]:
        raise ProviderRateLimitedError("opensky", "HTTP 429", 60)

    registry = ProviderRegistry(clock=FakeClock())
    registry.register(AIRCRAFT_STATES, StubAircraftFetcher(limited, name="opensky"))
    with pytest.raises(AllProvidersFailedError):
        await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    with pytest.raises(AllProvidersFailedError, match="cooling down for 60 s"):
        await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
