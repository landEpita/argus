"""
AISStream relay: one server-side websocket, many HTTP readers.

The browser never talks to aisstream.io — the key stays on the server (unlike
OSINT-War-Room, which shipped it to every visitor). A background task keeps
one subscription open, merges messages into :class:`VesselStore`, and the
``VESSEL_POSITIONS`` capability is served from that store.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any, Protocol

from pydantic import ValidationError

from argus.adapters.aisstream.messages import PositionUpdate, StaticUpdate, parse_message
from argus.domain.geo import GeoPoint
from argus.domain.maritime import Vessel, VesselQuery, ship_category
from argus.infra.clock import Clock, MonotonicClock, SystemWallClock, WallClock
from argus.infra.health import HealthRegistry
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderUnavailableError

logger = logging.getLogger(__name__)

DEFAULT_URL = "wss://stream.aisstream.io/v0/stream"
PROVIDER = "aisstream"
WORLD: tuple[tuple[tuple[float, float], tuple[float, float]], ...] = (
    ((-90.0, -180.0), (90.0, 180.0)),
)


# ── Store ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Static:
    name: str | None = None
    call_sign: str | None = None
    imo: str | None = None
    ship_type: int | None = None
    destination: str | None = None


class VesselStore:
    """Latest state per MMSI. Vessels not heard for ``max_age`` disappear."""

    def __init__(
        self,
        max_age: timedelta = timedelta(minutes=30),
        max_vessels: int = 200_000,
        clock: WallClock | None = None,
    ) -> None:
        self._max_age = max_age
        self._max_vessels = max_vessels
        self._clock = clock or SystemWallClock()
        self._positions: dict[str, PositionUpdate] = {}
        self._static: dict[str, _Static] = {}
        self.messages_applied = 0

    def __len__(self) -> int:
        return len(self._positions)

    def apply(self, update: PositionUpdate | StaticUpdate) -> None:
        self.messages_applied += 1
        if isinstance(update, PositionUpdate):
            if update.mmsi not in self._positions and len(self._positions) >= self._max_vessels:
                self.prune()
                if len(self._positions) >= self._max_vessels:
                    return  # full of fresh vessels; drop newcomers rather than grow unbounded
            self._positions[update.mmsi] = update
            if update.name and not self._static.get(update.mmsi, _Static()).name:
                self._static[update.mmsi] = replace(
                    self._static.get(update.mmsi, _Static()), name=update.name
                )
            return
        previous = self._static.get(update.mmsi, _Static())
        self._static[update.mmsi] = _Static(
            name=update.name or previous.name,
            call_sign=update.call_sign or previous.call_sign,
            imo=update.imo or previous.imo,
            ship_type=update.ship_type or previous.ship_type,
            destination=update.destination or previous.destination,
        )
        if len(self._static) > self._max_vessels * 2:
            for mmsi in [m for m in self._static if m not in self._positions]:
                del self._static[mmsi]

    def prune(self) -> int:
        cutoff = self._clock.utcnow() - self._max_age
        stale = [m for m, p in self._positions.items() if p.at < cutoff]
        for mmsi in stale:
            del self._positions[mmsi]
        return len(stale)

    def snapshot(self, query: VesselQuery) -> list[Vessel]:
        self.prune()
        vessels: list[Vessel] = []
        for mmsi, pos in self._positions.items():
            point = GeoPoint(lat=pos.lat, lon=pos.lon)
            if query.bbox is not None and not query.bbox.contains(point):
                continue
            static = self._static.get(mmsi, _Static())
            try:
                vessels.append(
                    Vessel(
                        mmsi=mmsi,
                        name=static.name or pos.name,
                        call_sign=static.call_sign,
                        imo=static.imo,
                        ship_type=static.ship_type,
                        category=ship_category(static.ship_type),
                        position=point,
                        speed_ms=pos.speed_ms,
                        course_deg=pos.course_deg,
                        heading_deg=pos.heading_deg,
                        destination=static.destination,
                        last_seen=pos.at,
                        source=PROVIDER,
                    )
                )
            except ValidationError:
                continue
        return vessels


# ── Websocket relay ──────────────────────────────────────────────────────────


class WebSocketLike(Protocol):
    async def send(self, message: str) -> None: ...

    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


Connector = Callable[[str], AbstractAsyncContextManager[WebSocketLike]]


def _default_connector(url: str) -> AbstractAsyncContextManager[WebSocketLike]:
    from websockets.asyncio.client import connect

    return connect(url, open_timeout=15, ping_interval=20, max_size=2**20)


class AisStreamRelay:
    """Background service. Reconnects forever with capped exponential backoff."""

    name = "aisstream-relay"
    HEALTH_EVERY_S = 10.0

    def __init__(
        self,
        api_key: str,
        store: VesselStore,
        *,
        health: HealthRegistry | None = None,
        bounding_boxes: Sequence[Sequence[Sequence[float]]] = WORLD,
        url: str = DEFAULT_URL,
        connector: Connector = _default_connector,
        clock: Clock | None = None,
        wall_clock: WallClock | None = None,
        backoff_initial_s: float = 1.0,
        backoff_max_s: float = 60.0,
    ) -> None:
        self._key = api_key
        self._store = store
        self._health = health
        self._boxes = [[list(corner) for corner in box] for box in bounding_boxes]
        self._url = url
        self._connect = connector
        self._clock = clock or MonotonicClock()
        self._wall = wall_clock or SystemWallClock()
        self._backoff_initial = backoff_initial_s
        self._backoff_max = backoff_max_s
        self._task: asyncio.Task[None] | None = None
        self._last_health = float("-inf")
        self.connected = False
        self.last_error: str | None = None

    def __repr__(self) -> str:
        return f"<AisStreamRelay connected={self.connected}>"

    def subscription(self) -> str:
        return json.dumps(
            {
                "APIKey": self._key,
                "BoundingBoxes": self._boxes,
                "FilterMessageTypes": [
                    "PositionReport",
                    "StandardClassBPositionReport",
                    "ExtendedClassBPositionReport",
                    "ShipStaticData",
                ],
            }
        )

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=self.name)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self.connected = False

    async def _run(self) -> None:
        delay = self._backoff_initial
        while True:
            try:
                await self.run_once()
                delay = self._backoff_initial  # clean close: reconnect promptly
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # any failure: record, back off, retry
                self._fail(f"{type(exc).__name__}: {exc}")
                delay = min(delay * 2, self._backoff_max)
            self.connected = False
            await asyncio.sleep(delay)

    async def run_once(self) -> None:
        """One connection lifetime. Returns when the server closes the stream."""
        async with self._connect(self._url) as ws:
            await ws.send(self.subscription())
            self.connected = True
            logger.info("aisstream connected")
            async for raw in ws:
                self.handle(raw)

    def handle(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if isinstance(message, dict) and "error" in message:
            # e.g. {"error": "Api Key Is Not Valid"}; the server closes right after.
            self._fail(str(message["error"]))
            return
        update = parse_message(message, now=self._wall.utcnow())
        if update is None:
            return
        self._store.apply(update)
        now = self._clock.now()
        if self._health is not None and now - self._last_health >= self.HEALTH_EVERY_S:
            self._health.record_success(PROVIDER)
            self._last_health = now
        self.last_error = None

    def _fail(self, error: str) -> None:
        self.last_error = error
        logger.warning("aisstream failure", extra={"error": error})
        if self._health is not None:
            self._health.record_failure(PROVIDER, error)
            self._last_health = float("-inf")


class VesselStoreFetcher(Fetcher[VesselQuery, list[Vessel]]):
    """Serves the capability from the relay's store; the I/O happens in the relay."""

    provider_name = PROVIDER

    def __init__(self, store: VesselStore, relay: AisStreamRelay) -> None:
        self._store = store
        self._relay = relay

    def transform_query(self, query: VesselQuery) -> Mapping[str, str]:
        return {}

    async def extract(self, params: Mapping[str, str]) -> Any:
        if len(self._store) == 0 and not self._relay.connected:
            raise ProviderUnavailableError(
                self.provider_name, self._relay.last_error or "stream not connected yet"
            )
        return None

    def transform(self, query: VesselQuery, raw: Any) -> list[Vessel]:
        return self._store.snapshot(query)
