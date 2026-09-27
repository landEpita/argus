from argus.infra.health import HealthRegistry, HealthStatus
from argus.infra.metrics import Metrics
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError
from argus.providers.observers import HealthObserver, MetricsObserver
from tests.fakes import FakeClock

CAP = "aviation.aircraft_states"


def test_metrics_observer_counts_outcomes_and_latency() -> None:
    metrics = Metrics()
    observer = MetricsObserver(metrics)
    observer.on_registered("opensky", CAP)
    observer.on_success("opensky", CAP, 0.2)
    observer.on_failure("opensky", CAP, ProviderUnavailableError("opensky", "x"), 5.0)
    observer.on_failure("opensky", CAP, ProviderResponseError("opensky", "x"), 0.1)

    def count(outcome: str) -> float | None:
        return metrics.registry.get_sample_value(
            "argus_provider_requests_total",
            {"provider": "opensky", "capability": CAP, "outcome": outcome},
        )

    assert (count("success"), count("unavailable"), count("bad_response")) == (1, 1, 1)
    latency = metrics.registry.get_sample_value(
        "argus_provider_request_duration_seconds_count", {"provider": "opensky", "capability": CAP}
    )
    assert latency == 3


def test_metrics_series_exist_at_zero_after_registration() -> None:
    metrics = Metrics()
    MetricsObserver(metrics).on_registered("opensky", CAP)
    assert b'outcome="unavailable",provider="opensky"} 0.0' in metrics.render()


def test_health_observer_forwards_to_registry() -> None:
    health = HealthRegistry(clock=FakeClock())
    observer = HealthObserver(health)
    observer.on_registered("opensky", CAP)
    observer.on_failure("opensky", CAP, ProviderUnavailableError("opensky", "timeout"), 1.0)
    [state] = health.snapshot()
    assert state.status is HealthStatus.FAILING
    assert state.last_error == "[opensky] timeout"
    observer.on_success("opensky", CAP, 0.1)
    assert health.snapshot()[0].status is HealthStatus.OK
