import csv
import io
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from argus.adapters.gdelt import GdeltConflictFetcher
from argus.adapters.gdelt.cameo import label
from argus.adapters.gdelt.fetcher import batch_timestamps, parse_export
from argus.domain.events import EventCategory, EventQuery
from argus.infra.cache import InMemoryTTLCache
from argus.providers.errors import ProviderResponseError, ProviderUnavailableError
from tests.fakes import StubHttp

FIXTURES = Path(__file__).parents[2] / "fixtures"
EXPORT = (FIXTURES / "gdelt_20260927160000.export.CSV.zip").read_bytes()
LASTUPDATE = (FIXTURES / "gdelt_lastupdate.txt").read_bytes()
LATEST = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)


def row(**cols: str) -> list[str]:
    """A 61-column export row: a located city-level fight unless overridden."""
    values = [""] * 61
    defaults = {
        0: "1",
        25: "1",
        26: "190",
        27: "190",
        28: "19",
        30: "-10.0",
        31: "3",
        32: "2",
        33: "3",
        51: "4",
        52: "Kharkiv, Ukraine",
        53: "UP",
        56: "49.98",
        57: "36.25",
        59: "20260927160000",
        60: "https://news.example/a",
    }
    for index, value in defaults.items():
        values[index] = value
    names = {
        "id": 0,
        "root_event": 25,
        "code": 26,
        "base": 27,
        "root": 28,
        "goldstein": 30,
        "articles": 33,
        "geo_type": 51,
        "lat": 56,
        "lon": 57,
    }
    for name, value in cols.items():
        values[names[name]] = value
    return values


def zipped(rows: list[list[str]]) -> bytes:
    text = io.StringIO()
    csv.writer(text, delimiter="\t", lineterminator="\n").writerows(rows)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("x.export.CSV", text.getvalue())
    return out.getvalue()


class TestParsing:
    def test_real_batch_keeps_only_located_violent_root_events(self) -> None:
        events = parse_export(EXPORT)
        assert events
        assert {e.category for e in events} == {EventCategory.ARMED_CONFLICT}
        assert all(e.details["location_precision"] != "unknown" for e in events)
        assert all(e.id.startswith("gdelt:") for e in events)
        assert all(
            e.details["reliability"] == "machine-coded from news; unverified" for e in events
        )

    def test_labels_and_severity(self) -> None:
        [event] = parse_export(zipped([row(code="194", base="194", goldstein="-8.0")]))
        assert event.title == "Fighting with artillery and tanks — Kharkiv, Ukraine"
        assert event.severity == pytest.approx(0.8)
        assert event.occurred_at == LATEST

    @pytest.mark.parametrize(
        "overrides",
        [
            {"root": "04", "base": "040", "code": "040"},  # consult: not violent
            {"root_event": "0"},  # not a root event
            {"geo_type": "1"},  # country centroid: would draw a fake cluster
            {"lat": ""},
        ],
    )
    def test_filters(self, overrides: dict[str, str]) -> None:
        assert parse_export(zipped([row(**overrides)])) == []

    def test_duplicates_at_one_place_are_merged_keeping_the_worst(self) -> None:
        events = parse_export(
            zipped(
                [
                    row(id="1", goldstein="-5.0", articles="2"),
                    row(id="2", goldstein="-10.0", articles="4"),
                    row(id="3", code="183", base="183", root="18"),
                ]
            )
        )
        assert len(events) == 2
        merged = next(e for e in events if e.details["cameo_code"] == "190")
        assert merged.id == "gdelt:2"
        assert merged.details["num_articles"] == 6

    def test_not_a_zip(self) -> None:
        with pytest.raises(ProviderResponseError):
            parse_export(b"<html>")

    def test_unknown_codes_fall_back_to_root_label(self) -> None:
        assert label("189", "18") == "Assault"
        assert label("999", "99") == "Violent event"


def test_batch_timestamps_cover_the_window_newest_first() -> None:
    stamps = batch_timestamps(LATEST, LATEST - timedelta(minutes=40))
    assert stamps == [LATEST - timedelta(minutes=m) for m in (0, 15, 30, 45)]
    assert len(batch_timestamps(LATEST, LATEST - timedelta(days=3))) == 96


class TestFetcher:
    def routes(self, missing: set[str] | None = None) -> StubHttp:
        missing = missing or set()

        def respond(url: str) -> bytes:
            if url.endswith("lastupdate.txt"):
                return LASTUPDATE
            name = url.rsplit("/", 1)[-1]
            if name in missing:
                raise ProviderUnavailableError("gdelt", "HTTP 404")
            return EXPORT

        http = StubHttp()
        http.payload = respond
        return http

    async def test_fetches_each_batch_once_thanks_to_the_batch_cache(self) -> None:
        http = self.routes()
        fetcher = GdeltConflictFetcher(http, InMemoryTTLCache(), base_url="https://gdelt.test")
        query = EventQuery(since=LATEST - timedelta(minutes=20))
        first = await fetcher.fetch(query)
        second = await fetcher.fetch(query)
        downloads = [u for u, _ in http.calls if u.endswith(".zip")]
        # 15:40 falls in the batch published at 15:30 (covering 15:30-15:45).
        assert downloads == [
            "https://gdelt.test/20260927160000.export.CSV.zip",
            "https://gdelt.test/20260927154500.export.CSV.zip",
            "https://gdelt.test/20260927153000.export.CSV.zip",
        ]
        assert len(first) == len(second) > 0

    async def test_a_missing_old_batch_is_skipped(self) -> None:
        http = self.routes(missing={"20260927154500.export.CSV.zip"})
        fetcher = GdeltConflictFetcher(http, InMemoryTTLCache(), base_url="https://gdelt.test")
        events = await fetcher.fetch(EventQuery(since=LATEST - timedelta(minutes=20)))
        assert events

    async def test_a_missing_latest_batch_fails(self) -> None:
        http = self.routes(missing={"20260927160000.export.CSV.zip"})
        fetcher = GdeltConflictFetcher(http, InMemoryTTLCache(), base_url="https://gdelt.test")
        with pytest.raises(ProviderUnavailableError):
            await fetcher.fetch(EventQuery(since=LATEST - timedelta(minutes=5)))

    async def test_unreadable_lastupdate(self) -> None:
        fetcher = GdeltConflictFetcher(StubHttp(b"nothing here"), InMemoryTTLCache())
        with pytest.raises(ProviderResponseError, match="lastupdate"):
            await fetcher.fetch(EventQuery(since=LATEST))
