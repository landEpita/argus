"""
GDELT 2.0 event exports — machine-coded events from world news, every 15 min.
https://www.gdeltproject.org/data.html#rawdatafiles

What this is, honestly: an automated coder reading news articles. It is fast
and global, and it is noisy — a soap-opera recap can be coded as a "fight".
To limit that, only *root* events of the violent categories with a
sub-national location are kept, and duplicates of the same event type at the
same place are merged (their article counts summed). Country-level locations
are dropped: GDELT puts them at the country's centroid, which would draw fake
clusters in the middle of countries. Severity comes from the Goldstein scale
(-10, most destabilising -> 1).

Each 15-minute batch is immutable once published, so parsed batches are
cached for a day and a rolling window costs one download per new batch.
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
import zipfile
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, clamp01
from argus.adapters.gdelt.cameo import VIOLENT_ROOT_CODES, label
from argus.domain.countries import country_index
from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.cache import Cache
from argus.infra.codec import PydanticCodec
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderError, ProviderResponseError

DEFAULT_BASE_URL = "http://data.gdeltproject.org/gdeltv2"
BATCH = timedelta(minutes=15)
MAX_BATCHES = 96  # 24 h
BATCH_TTL_S = 26 * 3600
MAX_BATCH_BYTES = 8 * 1024 * 1024
_TIMESTAMP = re.compile(r"/(\d{14})\.export\.CSV\.zip")
_CODEC: PydanticCodec[list[GeoEvent]] = PydanticCodec(list[GeoEvent])


class _Col(IntEnum):
    GLOBAL_EVENT_ID = 0
    ACTOR1_NAME = 6
    ACTOR2_NAME = 16
    IS_ROOT_EVENT = 25
    EVENT_CODE = 26
    EVENT_BASE_CODE = 27
    EVENT_ROOT_CODE = 28
    GOLDSTEIN = 30
    NUM_MENTIONS = 31
    NUM_SOURCES = 32
    NUM_ARTICLES = 33
    GEO_TYPE = 51
    GEO_NAME = 52
    GEO_COUNTRY = 53
    GEO_LAT = 56
    GEO_LON = 57
    DATE_ADDED = 59
    SOURCE_URL = 60


_COLUMNS = 61
_COUNTRY_LEVEL = "1"
_PRECISION = {"2": "state", "3": "city", "4": "city", "5": "state"}


def batch_timestamps(latest: datetime, since: datetime, limit: int = MAX_BATCHES) -> list[datetime]:
    """Batch start times from ``latest`` back to ``since``, newest first."""
    stamps: list[datetime] = []
    current = latest
    while current > since - BATCH and len(stamps) < limit:
        stamps.append(current)
        current -= BATCH
    return stamps


def parse_export(data: bytes) -> list[GeoEvent]:
    """One zipped export batch -> violent, located, de-duplicated events."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            name = archive.namelist()[0]
            text = archive.read(name).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, IndexError) as exc:
        raise ProviderResponseError("gdelt", "export batch is not a readable zip") from exc
    return merge_duplicates(
        _parse_row(row) for row in csv.reader(io.StringIO(text), delimiter="\t")
    )


def _parse_row(row: list[str]) -> GeoEvent | None:
    if len(row) < _COLUMNS:
        return None
    if row[_Col.EVENT_ROOT_CODE] not in VIOLENT_ROOT_CODES or row[_Col.IS_ROOT_EVENT] != "1":
        return None
    if row[_Col.GEO_TYPE] == _COUNTRY_LEVEL:
        return None
    lat, lon = as_float(row[_Col.GEO_LAT]), as_float(row[_Col.GEO_LON])
    if lat is None or lon is None:
        return None
    try:
        when = datetime.strptime(row[_Col.DATE_ADDED], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        goldstein = as_float(row[_Col.GOLDSTEIN])
        base, root = row[_Col.EVENT_BASE_CODE], row[_Col.EVENT_ROOT_CODE]
        place = row[_Col.GEO_NAME] or None
        title = label(base, root)
        return GeoEvent(
            id=f"gdelt:{row[_Col.GLOBAL_EVENT_ID]}",
            category=EventCategory.ARMED_CONFLICT,
            title=f"{title} — {place}" if place else title,
            position=GeoPoint(lat=lat, lon=lon),
            occurred_at=when,
            severity=None if goldstein is None else clamp01(-goldstein / 10),
            magnitude=goldstein,
            magnitude_unit="goldstein",
            url=row[_Col.SOURCE_URL] or None,
            source="gdelt",
            details={
                "cameo_code": row[_Col.EVENT_CODE],
                "actor1": row[_Col.ACTOR1_NAME] or None,
                "actor2": row[_Col.ACTOR2_NAME] or None,
                "country_fips": row[_Col.GEO_COUNTRY] or None,
                "country_iso2": country_index().country_of_place(place),
                "location_precision": _PRECISION.get(row[_Col.GEO_TYPE], "unknown"),
                "num_articles": int(row[_Col.NUM_ARTICLES] or 0),
                "num_sources": int(row[_Col.NUM_SOURCES] or 0),
                "reliability": "machine-coded from news; unverified",
            },
        )
    except (ValueError, ValidationError):
        return None


def merge_duplicates(events: Iterable[GeoEvent | None]) -> list[GeoEvent]:
    """Same CAMEO code at the same place in one batch = one event, articles summed."""
    merged: dict[tuple[Any, ...], GeoEvent] = {}
    for event in events:
        if event is None:
            continue
        key = (
            event.details["cameo_code"],
            round(event.position.lat, 3),
            round(event.position.lon, 3),
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = event
            continue
        articles = int(existing.details["num_articles"] or 0) + int(
            event.details["num_articles"] or 0
        )
        worst = max(existing, event, key=lambda e: e.severity or 0.0)
        merged[key] = worst.model_copy(
            update={"details": {**worst.details, "num_articles": articles}}
        )
    return list(merged.values())


class GdeltConflictFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "gdelt"

    def __init__(
        self,
        http: HttpClient,
        batch_cache: Cache,
        *,
        base_url: str = DEFAULT_BASE_URL,
        concurrency: int = 6,
    ) -> None:
        self._http = http
        self._cache = batch_cache
        self._base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(concurrency)

    def transform_query(self, query: EventQuery) -> Mapping[str, str]:
        return {"since": query.since.isoformat()}

    async def extract(self, params: Mapping[str, str]) -> Any:
        latest = await self._latest_batch()
        since = datetime.fromisoformat(params["since"])
        stamps = batch_timestamps(latest, since)
        results = await asyncio.gather(
            *(self._batch(stamp) for stamp in stamps), return_exceptions=True
        )
        batches: list[list[GeoEvent]] = []
        for stamp, result in zip(stamps, results, strict=True):
            if isinstance(result, ProviderError) and stamp != latest:
                continue  # an old batch missing upstream should not sink the window
            if isinstance(result, BaseException):
                raise result
            batches.append(result)
        return batches

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        return [event for batch in raw for event in batch]

    async def _latest_batch(self) -> datetime:
        body = await self._http.get_bytes(
            f"{self._base_url}/lastupdate.txt", provider=self.provider_name, max_bytes=4096
        )
        match = _TIMESTAMP.search(body.decode("ascii", errors="replace"))
        if not match:
            raise ProviderResponseError(self.provider_name, "lastupdate.txt has no export entry")
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)

    async def _batch(self, stamp: datetime) -> list[GeoEvent]:
        name = stamp.strftime("%Y%m%d%H%M%S")

        async def download() -> list[GeoEvent]:
            async with self._semaphore:
                data = await self._http.get_bytes(
                    f"{self._base_url}/{name}.export.CSV.zip",
                    provider=self.provider_name,
                    max_bytes=MAX_BATCH_BYTES,
                    timeout_s=30.0,
                )
            return parse_export(data)

        return await self._cache.get_or_set(f"gdelt:batch:{name}", BATCH_TTL_S, download, _CODEC)
