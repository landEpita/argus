"""
US Energy Information Administration, API v2 (``/v2/seriesid``).

Needs a key (free: https://www.eia.gov/opendata/register.php). ``DEMO_KEY``
works for a handful of requests per hour, enough for a few weekly series
refreshed every few hours.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from argus.adapters._util import as_float
from argus.domain.energy import EnergySeriesQuery, Reading
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://api.eia.gov/v2/seriesid"
WEEKS = 320  # a little over six years: five-year comparisons plus the chart


class EiaSeriesFetcher(Fetcher[EnergySeriesQuery, list[Reading]]):
    provider_name = "eia"

    def __init__(self, http: HttpClient, api_key: str, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._key = api_key
        self._base_url = base_url.rstrip("/")

    def transform_query(self, query: EnergySeriesQuery) -> Mapping[str, str]:
        return {"series": query.spec.eia_series, "length": str(WEEKS)}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            f"{self._base_url}/{params['series']}",
            provider=self.provider_name,
            params={"api_key": self._key, "length": params["length"]},
        )

    def transform(self, query: EnergySeriesQuery, raw: Any) -> list[Reading]:
        try:
            rows = raw["response"]["data"]
        except (KeyError, TypeError) as exc:
            raise ProviderResponseError(
                self.provider_name, f"{query.spec.eia_series}: unexpected payload"
            ) from exc
        readings: list[Reading] = []
        for row in rows:
            value, period = as_float(row.get("value")), row.get("period")
            if value is None or not isinstance(period, str):
                continue
            try:
                readings.append(Reading(period=date.fromisoformat(period), value=value))
            except ValueError:
                continue
        if not readings:
            raise ProviderResponseError(self.provider_name, f"{query.spec.eia_series}: no data")
        return readings
