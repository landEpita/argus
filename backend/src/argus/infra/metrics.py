"""
Prometheus metrics.

Each container owns its own ``CollectorRegistry`` so that several apps (and
every test) can coexist in one process without "duplicated timeseries" errors.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

_LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


class Metrics:
    content_type = CONTENT_TYPE_LATEST

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        self.provider_requests = Counter(
            "argus_provider_requests_total",
            "Upstream provider calls by outcome.",
            ["provider", "capability", "outcome"],
            registry=self.registry,
        )
        self.provider_latency = Histogram(
            "argus_provider_request_duration_seconds",
            "Upstream provider call duration.",
            ["provider", "capability"],
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.http_requests = Counter(
            "argus_http_requests_total",
            "HTTP requests served, by route template.",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.http_latency = Histogram(
            "argus_http_request_duration_seconds",
            "HTTP request duration, by route template.",
            ["method", "route"],
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.cache_events = Counter(
            "argus_cache_events_total",
            "Cache lookups by outcome (hit, miss, error).",
            ["cache", "outcome"],
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
