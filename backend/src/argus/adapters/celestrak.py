"""
CelesTrak GP data (OMM JSON), no key. https://celestrak.org/NORAD/documentation/gp-data-formats.php

CelesTrak asks clients not to fetch a group more than once every two hours;
the space service caches elements for that long.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from argus.adapters._util import parse_utc
from argus.domain.space import ElementsQuery, OrbitalElements
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"
# CelesTrak is often slow (observed 3-25 s for a few KB) but reliable; results
# are cached for two hours, so waiting is cheap and giving up is not.
TIMEOUT_S = 45.0


class CelestrakElementsFetcher(Fetcher[ElementsQuery, list[OrbitalElements]]):
    provider_name = "celestrak"

    def __init__(self, http: HttpClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._http = http
        self._url = base_url

    def transform_query(self, query: ElementsQuery) -> Mapping[str, str]:
        return {"GROUP": query.group.value, "FORMAT": "json"}

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            self._url, provider=self.provider_name, params=params, timeout_s=TIMEOUT_S
        )

    def transform(self, query: ElementsQuery, raw: Any) -> list[OrbitalElements]:
        if not isinstance(raw, list):
            # CelesTrak answers unknown groups with a plain-text message.
            raise ProviderResponseError(self.provider_name, "expected a JSON list of OMM records")
        parsed = (self._parse(record) for record in raw)
        return [e for e in parsed if e is not None]

    @staticmethod
    def _parse(record: Any) -> OrbitalElements | None:
        try:
            epoch = parse_utc(record["EPOCH"])
            if epoch is None:
                return None
            return OrbitalElements(
                norad_id=record["NORAD_CAT_ID"],
                name=str(record["OBJECT_NAME"]).strip(),
                international_designator=record.get("OBJECT_ID") or None,
                epoch=epoch,
                mean_motion_rev_per_day=record["MEAN_MOTION"],
                eccentricity=record["ECCENTRICITY"],
                inclination_deg=record["INCLINATION"],
                raan_deg=record["RA_OF_ASC_NODE"],
                arg_of_pericenter_deg=record["ARG_OF_PERICENTER"],
                mean_anomaly_deg=record["MEAN_ANOMALY"],
                bstar=record["BSTAR"],
                mean_motion_dot=record["MEAN_MOTION_DOT"],
                mean_motion_ddot=record["MEAN_MOTION_DDOT"],
            )
        except (KeyError, TypeError, ValidationError):
            return None
