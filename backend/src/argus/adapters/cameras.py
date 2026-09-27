"""
Open camera catalogs from road operators, all keyless.

Each operator publishes a list of its cameras; frames and streams are served
by the operator itself and loaded by the browser straight from there. Every
media URL is pinned to the operator's own host: a catalog cannot make the
browser load something from elsewhere.

- TfL JamCams: https://api.tfl.gov.uk/Place/Type/JamCam (stills + 10 s clips)
- Fintraffic weathercams: https://tie.digitraffic.fi/api/weathercam/v1/stations
- DriveBC: https://www.drivebc.ca/api/webcams/
- Transport for NSW: https://data.livetraffic.com/cameras/traffic-cam.json
- DelDOT: https://tmc.deldot.gov/json/videocamera.json (live HLS)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, ClassVar
from urllib.parse import urlsplit

from pydantic import ValidationError

from argus.adapters._util import as_float
from argus.domain.cameras import (
    NETWORKS,
    Camera,
    CameraNetwork,
    CameraQuery,
    FeedKind,
    facing_from_field,
    facing_from_title,
)
from argus.domain.geo import GeoPoint
from argus.infra.http import HttpClient
from argus.providers.base import Fetcher
from argus.providers.errors import ProviderResponseError

TFL_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
TFL_MEDIA = "https://s3-eu-west-1.amazonaws.com/jamcams.tfl.gov.uk/"
FINTRAFFIC_URL = "https://tie.digitraffic.fi/api/weathercam/v1/stations"
FINTRAFFIC_MEDIA = "https://weathercam.digitraffic.fi/"
DRIVEBC_URL = "https://www.drivebc.ca/api/webcams/"
DRIVEBC_MEDIA = "https://www.drivebc.ca/images/"
NSW_URL = "https://data.livetraffic.com/cameras/traffic-cam.json"
NSW_MEDIA = "https://webcams.transport.nsw.gov.au/"
DELDOT_URL = "https://tmc.deldot.gov/json/videocamera.json"
DELDOT_STREAM = re.compile(r"^https://video\.deldot\.gov(?::443)?/live/[\w.-]+/playlist\.m3u8$")
USER_AGENT = "argus (open-source OSINT dashboard)"


def _pinned(url: object, origin: str) -> str | None:
    """``url`` if it is an https URL under ``origin``, else None."""
    if not isinstance(url, str) or not url.startswith(origin):
        return None
    parts = urlsplit(url)
    return url if parts.scheme == "https" and ".." not in parts.path else None


def _point(lat: object, lon: object) -> GeoPoint | None:
    la, lo = as_float(lat), as_float(lon)
    if la is None or lo is None:
        return None
    try:
        return GeoPoint(lat=la, lon=lo)
    except ValidationError:
        return None


def _inside(network: CameraNetwork, point: GeoPoint) -> bool:
    return NETWORKS[network].coverage.contains(point)


class _CatalogFetcher(Fetcher[CameraQuery, list[Camera]]):
    """One GET of an operator's catalog; subclasses parse one entry."""

    network: CameraNetwork
    url: str
    headers: ClassVar[Mapping[str, str]] = {}
    list_key: ClassVar[str | None] = None  # where the list sits in a wrapping object

    def __init__(self, http: HttpClient, url: str | None = None) -> None:
        self._http = http
        self._url = url or self.url

    async def extract(self, params: Mapping[str, str]) -> Any:
        return await self._http.get_json(
            self._url, provider=self.provider_name, headers=self.headers, timeout_s=30
        )

    def transform(self, query: CameraQuery, raw: Any) -> list[Camera]:
        cameras: list[Camera] = []
        for entry in self._entries(raw):
            try:
                cameras.extend(self._parse(entry))
            except (KeyError, TypeError, AttributeError, ValidationError):
                continue
        return [c for c in cameras if _inside(self.network, c.position)]

    def _entries(self, raw: Any) -> list[Any]:
        entries = (
            (raw.get(self.list_key) if isinstance(raw, dict) else None) if self.list_key else raw
        )
        if not isinstance(entries, list):
            where = f"'{self.list_key}'" if self.list_key else "catalog"
            raise ProviderResponseError(self.provider_name, f"{where} is not a list")
        return entries

    def _parse(self, entry: Any) -> list[Camera]:
        raise NotImplementedError


class TflJamCamFetcher(_CatalogFetcher):
    provider_name = "tfl"
    network = CameraNetwork.TFL
    url = TFL_URL

    def _parse(self, entry: Any) -> list[Camera]:
        props = {p["key"]: p.get("value") for p in entry.get("additionalProperties") or []}
        if str(props.get("available")).lower() != "true":
            return []
        still = _pinned(props.get("imageUrl"), TFL_MEDIA)
        point = _point(entry.get("lat"), entry.get("lon"))
        raw_id = str(entry.get("id", "")).removeprefix("JamCams_")
        if still is None or point is None or not raw_id:
            return []
        clip = _pinned(props.get("videoUrl"), TFL_MEDIA)
        return [
            Camera(
                id=f"tfl:{raw_id}", network=self.network,
                name=str(entry.get("commonName") or f"JamCam {raw_id}"), position=point,
                heading_deg=facing_from_field(props.get("view")),
                feed=FeedKind.VIDEO if clip else FeedKind.IMAGE, url=clip or still,
                still_url=still, description=props.get("view") or None, source=self.provider_name,
            )
        ]  # fmt: skip


class FintrafficWeathercamFetcher(_CatalogFetcher):
    """One camera per preset (a station points several presets at the road)."""

    provider_name = "fintraffic"
    network = CameraNetwork.FINTRAFFIC
    url = FINTRAFFIC_URL
    list_key = "features"
    headers: ClassVar[Mapping[str, str]] = {"Digitraffic-User": USER_AGENT}

    def _parse(self, entry: Any) -> list[Camera]:
        props = entry["properties"]
        station = str(props.get("id", ""))
        if props.get("collectionStatus") != "GATHERING" or not station:
            return []
        lon, lat = entry["geometry"]["coordinates"][:2]
        point = _point(lat, lon)
        if point is None:
            return []
        name = str(props.get("name") or station).replace("_", " ")
        cameras = []
        for preset in props.get("presets") or []:
            preset_id = str(preset.get("id", ""))
            if preset.get("inCollection") is not True:
                continue
            if not re.fullmatch(r"C\d{7}", preset_id) or not preset_id.startswith(station):
                continue
            still = f"{FINTRAFFIC_MEDIA}{preset_id}.jpg"
            cameras.append(
                Camera(
                    id=f"fintraffic:{preset_id}",
                    network=self.network,
                    name=f"{name} · view {preset_id[-2:]}",
                    position=point,
                    feed=FeedKind.IMAGE,
                    url=still,
                    still_url=still,
                    source=self.provider_name,
                )
            )
        return cameras


class DriveBcWebcamFetcher(_CatalogFetcher):
    provider_name = "drivebc"
    network = CameraNetwork.DRIVEBC
    url = DRIVEBC_URL

    def _parse(self, entry: Any) -> list[Camera]:
        if entry.get("is_on") is not True or entry.get("should_appear") is False:
            return []
        lon, lat = entry["location"]["coordinates"][:2]
        point = _point(lat, lon)
        cam_id = entry["id"]
        if point is None or not isinstance(cam_id, int):
            return []
        still = f"{DRIVEBC_MEDIA}{cam_id}.jpg"
        return [
            Camera(
                id=f"drivebc:{cam_id}", network=self.network, name=str(entry.get("name") or cam_id),
                position=point, heading_deg=facing_from_field(entry.get("orientation")),
                feed=FeedKind.IMAGE, url=still, still_url=still,
                description=entry.get("caption") or None, source=self.provider_name,
            )
        ]  # fmt: skip


class NswTrafficCamFetcher(_CatalogFetcher):
    provider_name = "nsw"
    network = CameraNetwork.NSW
    url = NSW_URL
    list_key = "features"

    def _parse(self, entry: Any) -> list[Camera]:
        props = entry["properties"]
        still = _pinned(props.get("href"), NSW_MEDIA)
        lon, lat = entry["geometry"]["coordinates"][:2]
        point = _point(lat, lon)
        if still is None or point is None:
            return []
        return [
            Camera(
                id=f"nsw:{entry['id']}", network=self.network,
                name=str(props.get("title") or entry["id"]), position=point,
                heading_deg=facing_from_field(props.get("direction")), feed=FeedKind.IMAGE,
                url=still, still_url=still, description=props.get("view") or None,
                source=self.provider_name,
            )
        ]  # fmt: skip


class DelDotCameraFetcher(_CatalogFetcher):
    provider_name = "deldot"
    network = CameraNetwork.DELDOT
    url = DELDOT_URL
    list_key = "videoCameras"

    def _parse(self, entry: Any) -> list[Camera]:
        if entry.get("enabled") is not True or entry.get("status") != "Active":
            return []
        stream = entry["urls"].get("m3u8s")
        point = _point(entry.get("lat"), entry.get("lon"))
        if not isinstance(stream, str) or not DELDOT_STREAM.match(stream) or point is None:
            return []
        title = str(entry.get("title") or entry["id"])
        return [
            Camera(
                id=f"deldot:{entry['id']}", network=self.network, name=title, position=point,
                heading_deg=facing_from_title(title), feed=FeedKind.HLS, url=stream,
                description=entry.get("county") and f"{entry['county']} County",
                source=self.provider_name,
            )
        ]  # fmt: skip


FETCHERS: dict[CameraNetwork, type[_CatalogFetcher]] = {
    f.network: f
    for f in (
        TflJamCamFetcher,
        FintrafficWeathercamFetcher,
        DriveBcWebcamFetcher,
        NswTrafficCamFetcher,
        DelDotCameraFetcher,
    )
}
