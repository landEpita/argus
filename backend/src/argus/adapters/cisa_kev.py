"""CISA Known Exploited Vulnerabilities catalog (public JSON, no key)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import ValidationError

from argus.domain.cyber import ExploitedVulnerability, KevQuery
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

DEFAULT_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
RANSOMWARE = {"Known": True, "Unknown": None}


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


class CisaKevFetcher(Fetcher[KevQuery, list[ExploitedVulnerability]]):
    provider_name = "cisa-kev"

    def __init__(self, http: HttpClient, url: str = DEFAULT_URL) -> None:
        self._http = http
        self._url = url

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(self._url, provider=self.provider_name, timeout_s=30)

    def transform(self, query: KevQuery, raw: Any) -> list[ExploitedVulnerability]:
        if not isinstance(raw, dict) or not isinstance(raw.get("vulnerabilities"), list):
            raise ProviderResponseError(self.provider_name, "catalog has no 'vulnerabilities'")
        out: list[ExploitedVulnerability] = []
        for v in raw["vulnerabilities"]:
            try:
                added = _date(v.get("dateAdded"))
                if added is None:
                    continue
                out.append(
                    ExploitedVulnerability(
                        cve=v["cveID"],
                        vendor=v.get("vendorProject") or "Unknown",
                        product=v.get("product") or "Unknown",
                        name=v.get("vulnerabilityName") or v["cveID"],
                        description=v.get("shortDescription") or None,
                        date_added=added,
                        due_date=_date(v.get("dueDate")),
                        used_in_ransomware=RANSOMWARE.get(v.get("knownRansomwareCampaignUse")),
                        url=f"https://nvd.nist.gov/vuln/detail/{v['cveID']}",
                    )
                )
            except (KeyError, TypeError, ValidationError):
                continue
        return out
