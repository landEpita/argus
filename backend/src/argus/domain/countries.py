"""
Countries and mention detection.

Data: a slim extract of mledoze/countries (ODbL), shipped in ``argus/data``.
Detection is a longest-match gazetteer over names, official names, common
aliases, demonyms and capitals. It is automatic and imperfect ("Turkey" the
bird, "Georgia" the US state, "Jordan" the person): results are presented as
"countries mentioned", never as facts about where something happened.
"""

from __future__ import annotations

import json
import re
from functools import cache
from importlib import resources

from pydantic import Field

from argus.domain.base import DomainModel
from argus.domain.geo import GeoPoint

# Spellings the dataset lacks but the news uses constantly.
EXTRA_TERMS: dict[str, str] = {
    "U.S.": "US",
    "US": "US",
    "USA": "US",
    "UK": "GB",
    "Britain": "GB",
    "Kiev": "UA",
    "Crimea": "UA",
    "Donbas": "UA",
    "Gaza": "PS",
    "West Bank": "PS",
    "Palestinians": "PS",
    "North Korea": "KP",
    "South Korea": "KR",
    "Türkiye": "TR",
    "Turkey": "TR",  # the dataset now uses "Türkiye"
    "Taipei": "TW",
    "Kremlin": "RU",
    "Pentagon": "US",
    "White House": "US",
    "Beijing": "CN",
    "Tehran": "IR",
    "Hezbollah": "LB",
    "Houthis": "YE",
    "Houthi": "YE",
    "Congo": "CD",
}

# Terms that are country names but too often something else to count on their own.
# In world news "Turkey", "Chad" or "Niger" almost always mean the country; these rarely do.
AMBIGUOUS = frozenset({"Georgia", "Jordan", "Victoria"})


# USGS and GDELT name US places by state; a state means the United States.
US_STATES = frozenset(
    """Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida
    Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland Massachusetts
    Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon
    Pennsylvania Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming""".split()  # noqa: SIM905
) | {
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
    "Rhode Island", "South Carolina", "South Dakota", "West Virginia",
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY",
}  # fmt: skip


# Places that geocoders file under another state's country code (GDELT puts
# "Gaza" under Israel): when the place names one of these, it decides.
TERRITORY_OVERRIDES: dict[str, str] = {"Gaza": "PS", "West Bank": "PS", "Ramallah": "PS"}
_TERRITORY = re.compile(r"\b(" + "|".join(map(re.escape, TERRITORY_OVERRIDES)) + r")\b")


class Country(DomainModel):
    iso2: str = Field(pattern=r"^[A-Z]{2}$")
    iso3: str
    name: str
    official: str
    aliases: tuple[str, ...] = ()
    demonyms: tuple[str, ...] = ()
    capitals: tuple[str, ...] = ()
    centroid: GeoPoint
    region: str | None = None


class CountryIndex:
    def __init__(self, countries: list[Country]) -> None:
        self._by_iso2 = {c.iso2: c for c in countries}
        terms: dict[str, str] = {}
        for c in countries:
            for term in (c.name, c.official, *c.aliases, *c.demonyms, *c.capitals):
                if term and term not in AMBIGUOUS:
                    terms.setdefault(term, c.iso2)
            for demonym in c.demonyms:
                terms.setdefault(f"{demonym}s", c.iso2)  # "Iranians", "Israelis"
        for term, iso2 in EXTRA_TERMS.items():
            if iso2 in self._by_iso2:
                terms[term] = iso2
        self._terms = terms
        # Longest first, so "South Sudan" wins over "Sudan" at the same position.
        ordered = sorted(terms, key=len, reverse=True)
        self._pattern = re.compile(
            r"(?<![\w.])(?:" + "|".join(re.escape(t) for t in ordered) + r")(?![\w])"
        )

    def __len__(self) -> int:
        return len(self._by_iso2)

    def get(self, iso2: str) -> Country | None:
        return self._by_iso2.get(iso2.upper())

    def all(self) -> list[Country]:
        return list(self._by_iso2.values())

    def country_of_place(self, place: str | None) -> str | None:
        """
        The country of a place name written "…, Region, Country" (GDELT, USGS,
        GDACS). The last segment decides; failing that, the last country named.
        """
        if not place:
            return None
        territory = _TERRITORY.search(place)
        if territory:
            return TERRITORY_OVERRIDES[territory.group(1)]
        last = place.rsplit(",", 1)[-1].strip()
        if last in US_STATES:
            return "US"
        found = self.mentions(last) or self.mentions(place)
        return found[-1] if found else None

    def mentions(self, text: str) -> tuple[str, ...]:
        """ISO2 codes mentioned in ``text``, in order of first appearance."""
        seen: dict[str, None] = {}
        for match in self._pattern.finditer(text):
            seen.setdefault(self._terms[match.group(0)], None)
        return tuple(seen)


@cache
def country_index() -> CountryIndex:
    raw = json.loads(resources.files("argus.data").joinpath("countries.json").read_text("utf-8"))
    return CountryIndex(
        [
            Country(
                iso2=c["iso2"],
                iso3=c["iso3"],
                name=c["name"],
                official=c["official"],
                aliases=tuple(c["aliases"]),
                demonyms=tuple(c["demonyms"]),
                capitals=tuple(c["capitals"]),
                centroid=GeoPoint(lat=c["lat"], lon=c["lon"]),
                region=c["region"],
            )
            for c in raw["countries"]
        ]
    )
