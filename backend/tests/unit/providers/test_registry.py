import pytest

from argus.domain.aviation import AIRCRAFT_STATES, Aircraft, AircraftQuery
from argus.domain.capability import Capability
from argus.infra.health import HealthRegistry, HealthStatus
from argus.providers.errors import (
    AllProvidersFailedError,
    NoProviderError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    UnsupportedQueryError,
)
from argus.providers.observers import HealthObserver
from argus.providers.registry import ProviderRegistry
from tests.fakes import FakeClock, StubAircraftFetcher, make_aircraft


def failing(name: str, error: Exception | None = None) -> StubAircraftFetcher:
    def behaviour(_: AircraftQuery) -> list[Aircraft]:
        raise error or ProviderUnavailableError(name, "down")

    return StubAircraftFetcher(behaviour, name=name)


def working(name: str) -> StubAircraftFetcher:
    return StubAircraftFetcher(lambda _: [make_aircraft(source=name)], name=name)


@pytest.fixture
def health() -> HealthRegistry:
    return HealthRegistry(clock=FakeClock())


def registry_with(health: HealthRegistry) -> ProviderRegistry:
    return ProviderRegistry([HealthObserver(health)])


def statuses(health: HealthRegistry) -> dict[str, HealthStatus]:
    return {s.source: s.status for s in health.snapshot()}


async def test_raises_when_nothing_is_registered(health: HealthRegistry) -> None:
    with pytest.raises(NoProviderError, match=r"aviation\.aircraft_states"):
        await registry_with(health).fetch(AIRCRAFT_STATES, AircraftQuery())


async def test_lowest_priority_value_is_tried_first(health: HealthRegistry) -> None:
    registry = registry_with(health)
    registry.register(AIRCRAFT_STATES, working("backup"), priority=50)
    registry.register(AIRCRAFT_STATES, working("primary"), priority=10)
    [aircraft] = await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert aircraft.source == "primary"
    assert registry.providers_for(AIRCRAFT_STATES) == ["primary", "backup"]


@pytest.mark.parametrize("error_type", [ProviderUnavailableError, ProviderResponseError])
async def test_falls_back_on_provider_errors(
    health: HealthRegistry, error_type: type[ProviderError]
) -> None:
    registry = registry_with(health)
    registry.register(AIRCRAFT_STATES, failing("primary", error_type("primary", "x")), priority=10)
    registry.register(AIRCRAFT_STATES, working("backup"), priority=20)
    [aircraft] = await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert aircraft.source == "backup"
    assert statuses(health) == {"primary": HealthStatus.FAILING, "backup": HealthStatus.OK}


async def test_bugs_are_not_masked_by_fallback(health: HealthRegistry) -> None:
    registry = registry_with(health)
    registry.register(AIRCRAFT_STATES, failing("primary", KeyError("bug")), priority=10)
    registry.register(AIRCRAFT_STATES, working("backup"), priority=20)
    with pytest.raises(KeyError):
        await registry.fetch(AIRCRAFT_STATES, AircraftQuery())


async def test_all_failing_collects_every_error(health: HealthRegistry) -> None:
    registry = registry_with(health)
    registry.register(AIRCRAFT_STATES, failing("a"))
    registry.register(AIRCRAFT_STATES, failing("b"))
    with pytest.raises(AllProvidersFailedError) as info:
        await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert [e.provider for e in info.value.errors] == ["a", "b"]


def test_registering_marks_the_source_idle(health: HealthRegistry) -> None:
    registry_with(health).register(AIRCRAFT_STATES, working("opensky"))
    assert statuses(health) == {"opensky": HealthStatus.IDLE}


def test_capabilities_lists_providers_per_capability(health: HealthRegistry) -> None:
    registry = registry_with(health)
    other: Capability[AircraftQuery, list[Aircraft]] = Capability("aviation.other")
    registry.register(AIRCRAFT_STATES, working("opensky"))
    registry.register(other, working("adsblol"))
    assert registry.capabilities() == {
        "aviation.aircraft_states": ["opensky"],
        "aviation.other": ["adsblol"],
    }


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, ...]] = []

    def on_registered(self, provider: str, capability: str) -> None:
        self.events.append(("registered", provider))

    def on_success(self, provider: str, capability: str, duration_s: float) -> None:
        self.events.append(("success", provider, f"{duration_s:.1f}"))

    def on_failure(
        self, provider: str, capability: str, error: ProviderError, duration_s: float
    ) -> None:
        self.events.append(("failure", provider, f"{duration_s:.1f}"))


async def test_observers_see_every_outcome_with_its_duration() -> None:
    clock = FakeClock()
    observer = RecordingObserver()
    registry = ProviderRegistry([observer], clock=clock)

    def slow_failure(_: AircraftQuery) -> list[Aircraft]:
        clock.advance(2.5)
        raise ProviderUnavailableError("a", "timeout")

    def quick(_: AircraftQuery) -> list[Aircraft]:
        clock.advance(0.3)
        return []

    registry.register(AIRCRAFT_STATES, StubAircraftFetcher(slow_failure, name="a"), priority=1)
    registry.register(AIRCRAFT_STATES, StubAircraftFetcher(quick, name="b"), priority=2)
    await registry.fetch(AIRCRAFT_STATES, AircraftQuery())

    assert observer.events == [
        ("registered", "a"),
        ("registered", "b"),
        ("failure", "a", "2.5"),
        ("success", "b", "0.3"),
    ]


async def test_unsupported_queries_skip_silently_to_the_next_provider(
    health: HealthRegistry,
) -> None:
    def out_of_scope(_: AircraftQuery) -> list[Aircraft]:
        raise UnsupportedQueryError("adsblol", "needs a bounding box")

    registry = registry_with(health)
    registry.register(
        AIRCRAFT_STATES, StubAircraftFetcher(out_of_scope, name="adsblol"), priority=1
    )
    registry.register(AIRCRAFT_STATES, working("opensky"), priority=2)
    [aircraft] = await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert aircraft.source == "opensky"
    assert statuses(health) == {"adsblol": HealthStatus.IDLE, "opensky": HealthStatus.OK}


async def test_all_unsupported_is_flagged(health: HealthRegistry) -> None:
    def out_of_scope(_: AircraftQuery) -> list[Aircraft]:
        raise UnsupportedQueryError("adsblol", "needs a bounding box")

    registry = registry_with(health)
    registry.register(AIRCRAFT_STATES, StubAircraftFetcher(out_of_scope, name="adsblol"))
    with pytest.raises(AllProvidersFailedError) as info:
        await registry.fetch(AIRCRAFT_STATES, AircraftQuery())
    assert info.value.unsupported is True
