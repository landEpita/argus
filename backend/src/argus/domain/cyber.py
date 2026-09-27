"""Cyber: vulnerabilities known to be exploited in the wild."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability


class ExploitedVulnerability(DomainModel):
    cve: str = Field(pattern=r"^CVE-\d{4}-\d{4,}$")
    vendor: str
    product: str
    name: str
    description: str | None = None
    date_added: date
    due_date: date | None = None
    used_in_ransomware: bool | None = Field(default=None, description="None = unknown")
    url: str


class KevQuery(DomainModel):
    pass


EXPLOITED_VULNERABILITIES: Capability[KevQuery, list[ExploitedVulnerability]] = Capability(
    "cyber.exploited_vulnerabilities", "CVEs confirmed exploited in the wild (CISA KEV)."
)
