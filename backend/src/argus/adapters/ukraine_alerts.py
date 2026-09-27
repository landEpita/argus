"""
Ukrainian air-raid alerts via ubilling.net.ua/aerialalerts — a keyless,
community-run mirror of the official alert feed.

Honest limits, surfaced in every event's details:
- it is a mirror, not the official source (alerts.in.ua requires a token);
- it resolves to oblasts only, so each alert is drawn at the oblast's main
  city — it does not mean that city is the target;
- alert start times are often unknown (the mirror reports 1970), in which case
  only "active now" is claimed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from argus.domain.events import EventCategory, EventQuery, GeoEvent
from argus.domain.geo import GeoPoint
from argus.infra.clock import SystemWallClock, WallClock
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://ubilling.net.ua/aerialalerts/"
_PLAUSIBLE_SINCE = datetime(2022, 1, 1, tzinfo=UTC)

# Region -> (English name, main city latitude, longitude).
REGIONS: dict[str, tuple[str, float, float]] = {
    "Вінницька область": ("Vinnytsia oblast", 49.2331, 28.4682),
    "Волинська область": ("Volyn oblast", 50.7472, 25.3254),
    "Дніпропетровська область": ("Dnipropetrovsk oblast", 48.4647, 35.0462),
    "Донецька область": ("Donetsk oblast", 48.7389, 37.5848),
    "Житомирська область": ("Zhytomyr oblast", 50.2547, 28.6587),
    "Закарпатська область": ("Zakarpattia oblast", 48.6208, 22.2879),
    "Запорізька область": ("Zaporizhzhia oblast", 47.8388, 35.1396),
    "Івано-Франківська область": ("Ivano-Frankivsk oblast", 48.9226, 24.7111),
    "Київська область": ("Kyiv oblast", 49.7968, 30.1311),
    "Кіровоградська область": ("Kirovohrad oblast", 48.5079, 32.2623),
    "Луганська область": ("Luhansk oblast", 48.9483, 38.4917),
    "Львівська область": ("Lviv oblast", 49.8397, 24.0297),
    "Миколаївська область": ("Mykolaiv oblast", 46.9750, 31.9946),
    "Одеська область": ("Odesa oblast", 46.4825, 30.7233),
    "Полтавська область": ("Poltava oblast", 49.5883, 34.5514),
    "Рівненська область": ("Rivne oblast", 50.6199, 26.2516),
    "Сумська область": ("Sumy oblast", 50.9077, 34.7981),
    "Тернопільська область": ("Ternopil oblast", 49.5535, 25.5948),
    "Харківська область": ("Kharkiv oblast", 49.9935, 36.2304),
    "Херсонська область": ("Kherson oblast", 46.6354, 32.6169),
    "Хмельницька область": ("Khmelnytskyi oblast", 49.4229, 26.9871),
    "Черкаська область": ("Cherkasy oblast", 49.4444, 32.0598),
    "Чернівецька область": ("Chernivtsi oblast", 48.2921, 25.9358),
    "Чернігівська область": ("Chernihiv oblast", 51.4982, 31.2893),
    "м. Київ": ("Kyiv city", 50.4501, 30.5234),
    "Севастополь": ("Sevastopol", 44.6166, 33.5254),
    "АР Крим": ("Crimea", 44.9521, 34.1024),
}


class UkraineAlertsFetcher(Fetcher[EventQuery, list[GeoEvent]]):
    provider_name = "ubilling"

    def __init__(
        self, http: HttpClient, url: str = DEFAULT_URL, clock: WallClock | None = None
    ) -> None:
        self._http = http
        self._url = url
        self._clock = clock or SystemWallClock()

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name)

    def transform(self, query: EventQuery, raw: Any) -> list[GeoEvent]:
        if not isinstance(raw, dict) or not isinstance(raw.get("states"), dict):
            raise ProviderResponseError(self.provider_name, "payload has no 'states' map")
        observed = self._clock.utcnow()
        events: list[GeoEvent] = []
        for region, state in raw["states"].items():
            if not isinstance(state, dict) or state.get("alertnow") is not True:
                continue
            known = REGIONS.get(region)
            if known is None:
                logger.info("unknown alert region", extra={"region": region})
                continue
            name, lat, lon = known
            since = _parse_local(state.get("changed"))
            events.append(
                GeoEvent(
                    id=f"ua-alert:{name}",
                    category=EventCategory.AIR_RAID_ALERT,
                    title=f"Air-raid alert — {name}",
                    position=GeoPoint(lat=lat, lon=lon),
                    # "Active as of now": the alert may have started long before.
                    occurred_at=observed,
                    severity=None,
                    url="https://alerts.in.ua/en",
                    source=self.provider_name,
                    details={
                        "region": region,
                        "country_iso2": "UA",
                        "active_since": since.isoformat() if since else None,
                        "placement": "drawn at the oblast's main city, not a target",
                        "reliability": "community mirror of official alerts",
                    },
                )
            )
        return events


def _parse_local(value: Any) -> datetime | None:
    """The mirror reports Kyiv local time without an offset; 1970 means unknown."""
    if not isinstance(value, str):
        return None
    try:
        naive = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    aware = naive.replace(tzinfo=ZoneInfo("Europe/Kyiv")).astimezone(UTC)
    return aware if aware >= _PLAUSIBLE_SINCE else None
