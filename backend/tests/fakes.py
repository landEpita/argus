"""Hand-written test doubles shared across the suite."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from argus.domain.aviation import Aircraft, AircraftQuery
from argus.domain.geo import GeoPoint
from argus.providers.base import Fetcher


class FakeWallClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def utcnow(self) -> datetime:
        return self.now


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class StubHttp:
    """
    Returns a canned payload (or raises) and records every call.

    ``payload`` may be a function of the URL, for adapters that fetch several.
    """

    def __init__(self, payload: Any = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.posts: list[tuple[str, Any]] = []
        self.closed = False

    async def get_json(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> Any:
        self.calls.append((url, dict(params or {})))
        if self.error is not None:
            raise self.error
        return self.payload(url) if callable(self.payload) else self.payload

    async def get_bytes(
        self,
        url: str,
        *,
        provider: str,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        max_bytes: int = 0,
        timeout_s: float | None = None,
    ) -> bytes:
        self.calls.append((url, dict(params or {})))
        if self.error is not None:
            raise self.error
        payload = self.payload(url) if callable(self.payload) else self.payload
        return payload if isinstance(payload, bytes) else str(payload).encode()

    async def post_form(
        self,
        url: str,
        *,
        provider: str,
        data: Mapping[str, str],
        timeout_s: float | None = None,
    ) -> Any:
        self.calls.append((url, dict(data)))
        if self.error is not None:
            raise self.error
        return self.payload(url) if callable(self.payload) else self.payload

    async def post_json(
        self,
        url: str,
        *,
        provider: str,
        body: Any,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> Any:
        self.posts.append((url, body))
        if self.error is not None:
            raise self.error
        return self.payload(url) if callable(self.payload) else self.payload

    async def aclose(self) -> None:
        self.closed = True


class StubAircraftFetcher(Fetcher[AircraftQuery, list[Aircraft]]):
    """A fetcher whose behaviour is a plain function of the query."""

    provider_name = "stub"

    def __init__(
        self,
        behaviour: Callable[[AircraftQuery], list[Aircraft]],
        name: str = "stub",
    ) -> None:
        self._behaviour = behaviour
        self.provider_name = name
        self.queries: list[AircraftQuery] = []

    async def extract(self, params: Mapping[str, str]) -> Any:
        return None

    def transform(self, query: AircraftQuery, raw: Any) -> list[Aircraft]:
        self.queries.append(query)
        return self._behaviour(query)


def make_aircraft(
    icao24: str = "abc123",
    lat: float = 48.85,
    lon: float = 2.35,
    *,
    on_ground: bool = False,
    source: str = "stub",
) -> Aircraft:
    return Aircraft(
        icao24=icao24,
        callsign="TEST1",
        origin_country="France",
        position=GeoPoint(lat=lat, lon=lon),
        altitude_m=10_000.0,
        velocity_ms=230.0,
        heading_deg=90.0,
        vertical_rate_ms=0.0,
        on_ground=on_ground,
        last_contact=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        source=source,
    )
