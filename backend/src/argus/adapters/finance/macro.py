"""alternative.me crypto Fear & Greed, US Treasury par yields, ForexFactory calendar. No keys."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float, parse_utc
from argus.domain.macro import (
    CalendarEvent,
    EmptyQuery,
    Impact,
    SentimentIndex,
    SentimentReading,
    YieldCurve,
    YieldPoint,
)
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError


class CryptoFearGreedFetcher(Fetcher[EmptyQuery, list[SentimentIndex]]):
    provider_name = "alternative-me"

    def __init__(self, http: HttpClient, url: str = "https://api.alternative.me/fng/") -> None:
        self._http = http
        self._url = url

    def transform_query(self, query: EmptyQuery) -> Mapping[str, str]:
        return {"limit": "30"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name, params=params)

    def transform(self, query: EmptyQuery, raw: Any) -> list[SentimentIndex]:
        readings: list[SentimentReading] = []
        rows = raw.get("data") if isinstance(raw, dict) else None
        for row in rows if isinstance(rows, list) else []:
            value, ts = as_float(row.get("value")), as_float(row.get("timestamp"))
            if value is None or ts is None:
                continue
            try:
                readings.append(
                    SentimentReading(
                        value=int(value),
                        label=str(row.get("value_classification") or ""),
                        at=datetime.fromtimestamp(ts, tz=UTC),
                    )
                )
            except ValidationError:
                continue
        if not readings:
            raise ProviderResponseError(self.provider_name, "no readings")
        return [
            SentimentIndex(
                id="crypto-fear-greed",
                name="Crypto Fear & Greed",
                latest=readings[0],
                history=tuple(readings),
                source=self.provider_name,
            )
        ]


def _tenor_years(tenor: str) -> float | None:
    parts = tenor.replace("Month", "Mo").split()
    if len(parts) != 2:
        return None
    amount = as_float(parts[0])
    if amount is None:
        return None
    return (
        amount / 12 if parts[1].startswith("Mo") else amount if parts[1].startswith("Yr") else None
    )


def _points(header: list[str], row: list[str]) -> tuple[YieldPoint, ...]:
    points: list[YieldPoint] = []
    for tenor, cell in zip(header[1:], row[1:], strict=False):
        years, rate = _tenor_years(tenor), as_float(cell)
        if years is not None and rate is not None:
            points.append(YieldPoint(tenor=tenor, years=round(years, 4), rate_pct=rate))
    return tuple(sorted(points, key=lambda p: p.years))


class TreasuryYieldFetcher(Fetcher[EmptyQuery, YieldCurve]):
    provider_name = "us-treasury"
    URL = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        "daily-treasury-rates.csv/{year}/all"
    )

    def __init__(self, http: HttpClient, clock: WallClock | None = None) -> None:
        self._http = http
        self._clock = clock or SystemWallClock()

    def transform_query(self, query: EmptyQuery) -> Mapping[str, str]:
        year = str(self._clock.utcnow().year)
        return {
            "year": year,
            "type": "daily_treasury_yield_curve",
            "field_tdr_date_value": year,
            "_format": "csv",
        }

    async def extract(self, params: Mapping[str, str]) -> Any:
        url = self.URL.format(year=params["year"])
        query = {k: v for k, v in params.items() if k != "year"}
        # The Treasury site is slow (10 s and more observed); results are cached for hours.
        return await self._http.get_bytes(
            url, provider=self.provider_name, params=query, timeout_s=45
        )

    def transform(self, query: EmptyQuery, raw: Any) -> YieldCurve:
        text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else str(raw)
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2 or not rows[0] or rows[0][0] != "Date":
            raise ProviderResponseError(self.provider_name, "unexpected CSV")
        header, latest = rows[0], rows[1]  # newest first
        try:
            day = datetime.strptime(latest[0], "%m/%d/%Y").date()
        except ValueError as exc:
            raise ProviderResponseError(self.provider_name, "bad date") from exc
        points = _points(header, latest)
        by_tenor = {p.tenor: p.rate_pct for p in points}
        two, ten = by_tenor.get("2 Yr"), by_tenor.get("10 Yr")
        return YieldCurve(
            date=day,
            points=points,
            previous=_points(header, rows[2]) if len(rows) > 2 else (),
            inverted_2y_10y=None if two is None or ten is None else two > ten,
            source=self.provider_name,
        )


IMPACTS = {
    "High": Impact.HIGH,
    "Medium": Impact.MEDIUM,
    "Low": Impact.LOW,
    "Holiday": Impact.HOLIDAY,
}


class ForexFactoryCalendarFetcher(Fetcher[EmptyQuery, list[CalendarEvent]]):
    provider_name = "forexfactory"

    def __init__(
        self, http: HttpClient, url: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    ) -> None:
        self._http = http
        self._url = url

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name)

    def transform(self, query: EmptyQuery, raw: Any) -> list[CalendarEvent]:
        if not isinstance(raw, list):
            raise ProviderResponseError(self.provider_name, "expected a list")
        events: list[CalendarEvent] = []
        for row in raw:
            at = parse_utc(row.get("date")) if isinstance(row, dict) else None
            impact = IMPACTS.get(str(row.get("impact"))) if isinstance(row, dict) else None
            if at is None or impact is None:
                continue
            try:
                events.append(
                    CalendarEvent(
                        title=row.get("title") or "",
                        currency=row.get("country") or "",
                        at=at.astimezone(UTC),
                        impact=impact,
                        forecast=row.get("forecast") or None,
                        previous=row.get("previous") or None,
                    )
                )
            except ValidationError:
                continue
        return sorted(events, key=lambda e: e.at)
