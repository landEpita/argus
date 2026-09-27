from argus.infra.health import HealthRegistry, HealthStatus
from tests.fakes import FakeClock


def status_of(registry: HealthRegistry, source: str) -> HealthStatus:
    return next(s.status for s in registry.snapshot() if s.source == source)


def test_registered_but_never_called_is_idle() -> None:
    registry = HealthRegistry(clock=FakeClock())
    registry.register("opensky")
    assert status_of(registry, "opensky") is HealthStatus.IDLE


def test_success_is_ok_then_stale() -> None:
    clock = FakeClock()
    registry = HealthRegistry(clock=clock, stale_after_s=60)
    registry.record_success("opensky")
    assert status_of(registry, "opensky") is HealthStatus.OK
    clock.advance(61)
    assert status_of(registry, "opensky") is HealthStatus.STALE


def test_failure_reports_error_and_success_clears_it() -> None:
    registry = HealthRegistry(clock=FakeClock())
    registry.record_failure("opensky", "timeout")
    registry.record_failure("opensky", "HTTP 503")
    [health] = registry.snapshot()
    assert health.status is HealthStatus.FAILING
    assert health.last_error == "HTTP 503"
    assert health.consecutive_failures == 2

    registry.record_success("opensky")
    [health] = registry.snapshot()
    assert health.status is HealthStatus.OK
    assert health.last_error is None
    assert health.consecutive_failures == 0


def test_register_does_not_reset_existing_state() -> None:
    registry = HealthRegistry(clock=FakeClock())
    registry.record_success("opensky")
    registry.register("opensky")
    assert status_of(registry, "opensky") is HealthStatus.OK


def test_snapshot_is_sorted_by_source() -> None:
    registry = HealthRegistry(clock=FakeClock())
    for name in ("zeta", "alpha", "mid"):
        registry.register(name)
    assert [s.source for s in registry.snapshot()] == ["alpha", "mid", "zeta"]
