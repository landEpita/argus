"""
Geolocated events: earthquakes, fires, storms, disaster alerts, reported
conflict. One normalised shape so the API and the map treat every feed alike.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, Field

from argus.domain.base import DomainModel
from argus.domain.capability import Capability
from argus.domain.geo import BoundingBox, GeoPoint

DetailValue = str | int | float | bool | None


class EventCategory(StrEnum):
    EARTHQUAKE = "earthquake"
    TSUNAMI = "tsunami"
    VOLCANO = "volcano"
    WILDFIRE = "wildfire"
    FIRE_HOTSPOT = "fire_hotspot"
    TROPICAL_CYCLONE = "tropical_cyclone"
    SEVERE_STORM = "severe_storm"
    FLOOD = "flood"
    DROUGHT = "drought"
    LANDSLIDE = "landslide"
    SEA_ICE = "sea_ice"
    DUST_HAZE = "dust_haze"
    EXTREME_TEMPERATURE = "extreme_temperature"
    ARMED_CONFLICT = "armed_conflict"
    AIR_RAID_ALERT = "air_raid_alert"
    LAUNCH = "launch"
    INTERNET_OUTAGE = "internet_outage"
    OTHER = "other"


class GeoEvent(DomainModel):
    id: str = Field(description="Stable id, prefixed by source: 'usgs:us7000abcd'")
    category: EventCategory
    title: str
    position: GeoPoint
    occurred_at: datetime = Field(description="When it happened, or last update if ongoing")
    severity: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Normalised 0..1 for styling; each feed documents how it is derived",
    )
    magnitude: float | None = None
    magnitude_unit: str | None = None
    url: str | None = None
    source: str
    details: dict[str, DetailValue] = Field(default_factory=dict)


class EventQuery(DomainModel):
    bbox: BoundingBox | None = None
    since: AwareDatetime


class EventFeed(StrEnum):
    EARTHQUAKES = "earthquakes"
    NATURAL_EVENTS = "natural-events"
    DISASTER_ALERTS = "disaster-alerts"
    FIRES = "fires"
    CONFLICT = "conflict"
    AIR_ALERTS = "air-alerts"
    LAUNCHES = "launches"
    INTERNET_OUTAGES = "internet-outages"


def _feed(feed: EventFeed, description: str) -> Capability[EventQuery, list[GeoEvent]]:
    return Capability(f"events.{feed.value}", description)


EARTHQUAKES = _feed(EventFeed.EARTHQUAKES, "Recent earthquakes (seismic networks).")
NATURAL_EVENTS = _feed(EventFeed.NATURAL_EVENTS, "Open natural events tracked by NASA EONET.")
DISASTER_ALERTS = _feed(EventFeed.DISASTER_ALERTS, "GDACS disaster alerts with alert levels.")
FIRES = _feed(EventFeed.FIRES, "Satellite thermal-anomaly detections (fire hotspots).")
CONFLICT = _feed(
    EventFeed.CONFLICT,
    "Media-reported violent events, machine-coded. Noisy: treat as leads, not facts.",
)

AIR_ALERTS = _feed(
    EventFeed.AIR_ALERTS, "Active air-raid alerts, one event per region under alert."
)
LAUNCHES = _feed(EventFeed.LAUNCHES, "Orbital launches from the window start onwards.")
INTERNET_OUTAGES = _feed(
    EventFeed.INTERNET_OUTAGES, "Country-level drops in Internet reachability signals."
)

FEED_CAPABILITIES: dict[EventFeed, Capability[EventQuery, list[GeoEvent]]] = {
    EventFeed.EARTHQUAKES: EARTHQUAKES,
    EventFeed.NATURAL_EVENTS: NATURAL_EVENTS,
    EventFeed.DISASTER_ALERTS: DISASTER_ALERTS,
    EventFeed.FIRES: FIRES,
    EventFeed.CONFLICT: CONFLICT,
    EventFeed.AIR_ALERTS: AIR_ALERTS,
    EventFeed.LAUNCHES: LAUNCHES,
    EventFeed.INTERNET_OUTAGES: INTERNET_OUTAGES,
}
