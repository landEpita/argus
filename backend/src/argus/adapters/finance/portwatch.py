"""
IMF PortWatch (ArcGIS feature services), no key.
https://portwatch.imf.org — daily vessel transits from AIS, published with a delay of days.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.domain.chokepoints import ChokepointQuery, ChokepointTraffic, DailyTransits, summarise
from argus.domain.geo import GeoPoint
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
CHOKEPOINTS_URL = f"{BASE}/PortWatch_chokepoints_database/FeatureServer/0/query"
DAILY_URL = f"{BASE}/Daily_Chokepoints_Data/FeatureServer/0/query"
PAGE = 2000
MAX_PAGES = 15
LOOKBACK_DAYS = 380  # a year plus a week, for the same-week-last-year baseline


class PortWatchFetcher(Fetcher[ChokepointQuery, list[ChokepointTraffic]]):
    provider_name = "portwatch"

    def __init__(self, http: HttpClient, clock: WallClock | None = None) -> None:
        self._http = http
        self._clock = clock or SystemWallClock()

    def transform_query(self, query: ChokepointQuery) -> Mapping[str, str]:
        since = self._clock.utcnow().date() - timedelta(days=LOOKBACK_DAYS)
        return {"since": since.isoformat()}

    async def extract(self, params: Mapping[str, str]) -> Any:
        chokepoints, daily = await asyncio.gather(
            self._http.get_json(
                CHOKEPOINTS_URL,
                provider=self.provider_name,
                params={"where": "1=1", "outFields": "portid,portname,lat,lon", "f": "json"},
                timeout_s=30,
            ),
            self._daily(params["since"]),
        )
        return {"chokepoints": chokepoints, "daily": daily}

    async def _daily(self, since: str) -> list[Any]:
        rows: list[Any] = []
        for page in range(MAX_PAGES):
            body = await self._http.get_json(
                DAILY_URL,
                provider=self.provider_name,
                params={
                    "where": f"date >= DATE '{since}'",
                    "outFields": "date,portid,n_total,n_tanker",
                    "orderByFields": "date ASC",
                    "resultOffset": str(page * PAGE),
                    "resultRecordCount": str(PAGE),
                    "f": "json",
                },
                timeout_s=30,
            )
            features = body.get("features") if isinstance(body, dict) else None
            if not isinstance(features, list):
                raise ProviderResponseError(self.provider_name, "daily query returned no features")
            rows.extend(features)
            if len(features) < PAGE and not body.get("exceededTransferLimit"):
                break
        return rows

    def transform(self, query: ChokepointQuery, raw: Any) -> list[ChokepointTraffic]:
        points = (raw.get("chokepoints") or {}).get("features") if isinstance(raw, dict) else None
        if not isinstance(points, list):
            raise ProviderResponseError(self.provider_name, "no chokepoint list")
        series: dict[str, list[DailyTransits]] = defaultdict(list)
        for feature in raw.get("daily") or []:
            a = feature.get("attributes") or {}
            day = _date(a.get("date"))
            total, tankers = as_float(a.get("n_total")), as_float(a.get("n_tanker"))
            if day is None or total is None:
                continue
            try:
                series[str(a.get("portid"))].append(
                    DailyTransits(date=day, total=int(total), tankers=int(tankers or 0))
                )
            except ValidationError:
                continue
        result: list[ChokepointTraffic] = []
        for feature in points:
            a = feature.get("attributes") or {}
            lat, lon = as_float(a.get("lat")), as_float(a.get("lon"))
            port = str(a.get("portid"))
            if lat is None or lon is None or port not in series:
                continue
            summary = summarise(
                port,
                str(a.get("portname")),
                GeoPoint(lat=lat, lon=lon),
                series[port],
                self.provider_name,
            )
            if summary is not None:
                result.append(summary)
        return result


def _date(value: Any) -> date | None:
    """ArcGIS returns dates either as 'YYYY-MM-DD' strings or as epoch milliseconds."""
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    number = as_float(value)
    return None if number is None else datetime.fromtimestamp(number / 1000, tz=UTC).date()
