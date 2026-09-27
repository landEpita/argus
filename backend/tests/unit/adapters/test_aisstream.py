import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from argus.adapters.aisstream import AisStreamRelay, VesselStore, VesselStoreFetcher
from argus.adapters.aisstream.messages import PositionUpdate, StaticUpdate, parse_message
from argus.domain.geo import BoundingBox
from argus.domain.maritime import ShipCategory, VesselQuery, ship_category
from argus.infra.health import HealthRegistry, HealthStatus
from argus.providers.errors import ProviderUnavailableError
from tests.fakes import FakeClock, FakeWallClock

NOW = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


def position(
    mmsi: int = 227006760, lat: float = 43.3, lon: float = 5.35, **body: Any
) -> dict[str, Any]:
    report = {
        "Cog": 123.4,
        "Sog": 12.0,
        "TrueHeading": 120,
        "Latitude": lat,
        "Longitude": lon,
        **body,
    }
    return {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": mmsi,
            "ShipName": "MARIUS@@@@ ",
            "latitude": lat,
            "longitude": lon,
            "time_utc": "2026-09-27 15:59:30.123456789 +0000 UTC",
        },
        "Message": {"PositionReport": report},
    }


def static(mmsi: int = 227006760, type_code: int = 80) -> dict[str, Any]:
    return {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": mmsi, "ShipName": "MARIUS"},
        "Message": {
            "ShipStaticData": {
                "Name": "MARIUS",
                "CallSign": "FABC ",
                "ImoNumber": 9123456,
                "Type": type_code,
                "Destination": "FOS SUR MER@@",
            }
        },
    }


class TestMessages:
    def test_position_report_in_si_units(self) -> None:
        update = parse_message(position(), now=NOW)
        assert isinstance(update, PositionUpdate)
        assert update.mmsi == "227006760"
        assert update.speed_ms == pytest.approx(6.17, abs=0.01)
        assert (update.course_deg, update.heading_deg) == (123.4, 120)
        assert update.name == "MARIUS"
        assert update.at == datetime(2026, 9, 27, 15, 59, 30, 123456, tzinfo=UTC)

    def test_not_available_sentinels_become_none(self) -> None:
        update = parse_message(position(Sog=102.3, Cog=360, TrueHeading=511), now=NOW)
        assert isinstance(update, PositionUpdate)
        assert (update.speed_ms, update.course_deg, update.heading_deg) == (None, None, None)

    def test_static_data(self) -> None:
        update = parse_message(static(), now=NOW)
        assert update == StaticUpdate(
            mmsi="227006760",
            name="MARIUS",
            call_sign="FABC",
            imo="9123456",
            ship_type=80,
            destination="FOS SUR MER",
        )

    @pytest.mark.parametrize(
        "message",
        [
            None,
            {"MessageType": "PositionReport", "MetaData": {"MMSI": 12}},
            position(lat=91, lon=181),
            {"MessageType": "Interrogation", "MetaData": {"MMSI": 227006760}, "Message": {}},
        ],
    )
    def test_ignored(self, message: Any) -> None:
        assert parse_message(message, now=NOW) is None

    def test_bad_timestamp_falls_back_to_now(self) -> None:
        msg = position()
        msg["MetaData"]["time_utc"] = "yesterday"
        update = parse_message(msg, now=NOW)
        assert isinstance(update, PositionUpdate)
        assert update.at == NOW


@pytest.mark.parametrize(
    ("code", "category"),
    [
        (None, ShipCategory.UNKNOWN),
        (30, ShipCategory.FISHING),
        (35, ShipCategory.MILITARY),
        (52, ShipCategory.TUG),
        (55, ShipCategory.LAW_ENFORCEMENT),
        (37, ShipCategory.PLEASURE),
        (41, ShipCategory.HIGH_SPEED),
        (60, ShipCategory.PASSENGER),
        (70, ShipCategory.CARGO),
        (84, ShipCategory.TANKER),
        (99, ShipCategory.OTHER),
    ],
)
def test_ship_categories(code: int | None, category: ShipCategory) -> None:
    assert ship_category(code) is category


class TestStore:
    def store(self, clock: FakeWallClock | None = None, **kwargs: Any) -> VesselStore:
        return VesselStore(clock=clock or FakeWallClock(NOW), **kwargs)

    def test_merges_static_and_position(self) -> None:
        store = self.store()
        store.apply(parse_message(static(), now=NOW))  # type: ignore[arg-type]
        store.apply(parse_message(position(), now=NOW))  # type: ignore[arg-type]
        [vessel] = store.snapshot(VesselQuery())
        assert vessel.category is ShipCategory.TANKER
        assert (vessel.name, vessel.imo, vessel.destination) == ("MARIUS", "9123456", "FOS SUR MER")

    def test_stale_vessels_disappear(self) -> None:
        clock = FakeWallClock(NOW)
        store = self.store(clock, max_age=timedelta(minutes=10))
        store.apply(parse_message(position(), now=NOW))  # type: ignore[arg-type]
        clock.now = NOW + timedelta(minutes=11)
        assert store.snapshot(VesselQuery()) == []

    def test_bbox_filter(self) -> None:
        store = self.store()
        store.apply(parse_message(position(mmsi=111111111, lat=43, lon=5), now=NOW))  # type: ignore[arg-type]
        store.apply(parse_message(position(mmsi=222222222, lat=1, lon=100), now=NOW))  # type: ignore[arg-type]
        box = BoundingBox(west=0, south=40, east=10, north=50)
        assert [v.mmsi for v in store.snapshot(VesselQuery(bbox=box))] == ["111111111"]

    def test_capacity_is_bounded(self) -> None:
        store = self.store(max_vessels=2)
        for i in range(3):
            store.apply(parse_message(position(mmsi=100000000 + i), now=NOW))  # type: ignore[arg-type]
        assert len(store) == 2


class FakeSocket:
    def __init__(self, messages: list[Any]) -> None:
        self.sent: list[str] = []
        self._messages = [m if isinstance(m, str) else json.dumps(m) for m in messages]

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def __aiter__(self) -> AsyncIterator[str]:
        for message in self._messages:
            yield message


def connector(
    *sockets: FakeSocket | Exception,
) -> Callable[[str], AbstractAsyncContextManager[FakeSocket]]:
    queue = list(sockets)

    @asynccontextmanager
    async def connect(url: str) -> AsyncIterator[FakeSocket]:
        item = queue.pop(0) if queue else FakeSocket([])
        if isinstance(item, Exception):
            raise item
        yield item

    return connect


class TestRelay:
    def relay(
        self, store: VesselStore, health: HealthRegistry, *sockets: FakeSocket | Exception
    ) -> AisStreamRelay:
        return AisStreamRelay(
            "KEY",
            store,
            health=health,
            connector=connector(*sockets),
            clock=FakeClock(),
            wall_clock=FakeWallClock(NOW),
            backoff_initial_s=0.001,
            backoff_max_s=0.002,
        )

    async def test_subscribes_then_feeds_the_store(self) -> None:
        store, health = VesselStore(clock=FakeWallClock(NOW)), HealthRegistry(clock=FakeClock())
        socket = FakeSocket([static(), position(), "not json", {"MessageType": "Unknown"}])
        relay = self.relay(store, health, socket)
        await relay.run_once()
        subscription = json.loads(socket.sent[0])
        assert subscription["APIKey"] == "KEY"
        assert subscription["BoundingBoxes"] == [[[-90.0, -180.0], [90.0, 180.0]]]
        assert "ShipStaticData" in subscription["FilterMessageTypes"]
        assert len(store) == 1
        assert health.snapshot()[0].status is HealthStatus.OK

    async def test_server_error_message_is_reported(self) -> None:
        store, health = VesselStore(clock=FakeWallClock(NOW)), HealthRegistry(clock=FakeClock())
        relay = self.relay(store, health, FakeSocket([{"error": "Api Key Is Not Valid"}]))
        await relay.run_once()
        assert relay.last_error == "Api Key Is Not Valid"
        assert health.snapshot()[0].status is HealthStatus.FAILING

    async def test_reconnects_after_failures(self) -> None:
        store, health = VesselStore(clock=FakeWallClock(NOW)), HealthRegistry(clock=FakeClock())
        relay = self.relay(
            store, health, OSError("refused"), OSError("refused"), FakeSocket([position()])
        )
        await relay.start()
        for _ in range(200):
            if len(store):
                break
            await asyncio.sleep(0.005)
        await relay.stop()
        assert len(store) == 1
        assert relay.connected is False
        await relay.stop()  # idempotent

    def test_repr_hides_the_key(self) -> None:
        relay = self.relay(VesselStore(), HealthRegistry())
        assert "KEY" not in repr(relay)


class TestStoreFetcher:
    async def test_unavailable_until_connected_or_populated(self) -> None:
        store = VesselStore(clock=FakeWallClock(NOW))
        relay = AisStreamRelay("KEY", store, connector=connector())
        fetcher = VesselStoreFetcher(store, relay)
        with pytest.raises(ProviderUnavailableError, match="not connected"):
            await fetcher.fetch(VesselQuery())
        store.apply(parse_message(position(), now=NOW))  # type: ignore[arg-type]
        assert len(await fetcher.fetch(VesselQuery())) == 1
