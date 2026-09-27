"""Open camera catalogs against recorded payloads."""

import json
from pathlib import Path
from typing import Any

import pytest

from argus.adapters.cameras import (
    DelDotCameraFetcher,
    DriveBcWebcamFetcher,
    FintrafficWeathercamFetcher,
    NswTrafficCamFetcher,
    TflJamCamFetcher,
)
from argus.domain.cameras import CameraQuery, FeedKind
from argus.providers.errors import ProviderResponseError
from tests.fakes import StubHttp

FIXTURES = Path(__file__).parents[2] / "fixtures"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


async def test_tfl_serves_clips_and_states_facing_only_when_given() -> None:
    cams = await TflJamCamFetcher(StubHttp(load("tfl_jamcams.json"))).fetch(CameraQuery())
    assert len(cams) == 3  # the unavailable one is dropped
    first = cams[0]
    assert (first.id, first.name, first.heading_deg) == (
        "tfl:00002.00865",
        "A406 Billet Upass E",
        270,
    )
    assert first.feed is FeedKind.VIDEO
    assert first.url.endswith("00002.00865.mp4")
    assert first.still_url is not None
    assert first.still_url.endswith(".jpg")
    home = next(c for c in cams if c.description == "Home")
    assert home.heading_deg is None  # "Home" is a preset, not a direction
    assert next(c for c in cams if c.description and "East" in c.description).heading_deg == 135


async def test_fintraffic_one_camera_per_preset() -> None:
    http = StubHttp(load("fintraffic_stations.json"))
    cams = await FintrafficWeathercamFetcher(http).fetch(CameraQuery())
    assert [c.id for c in cams][:3] == [
        "fintraffic:C0150301", "fintraffic:C0150302", "fintraffic:C0150309",
    ]  # fmt: skip
    assert cams[0].url == "https://weathercam.digitraffic.fi/C0150301.jpg"
    assert all(c.heading_deg is None for c in cams)  # the catalog states no facing
    assert all(not c.id.startswith("fintraffic:C" + "0" * 7) for c in cams)
    assert FintrafficWeathercamFetcher.headers["Digitraffic-User"]


async def test_drivebc_orientation_and_switched_off_cameras() -> None:
    cams = await DriveBcWebcamFetcher(StubHttp(load("drivebc_webcams.json"))).fetch(CameraQuery())
    assert [(c.id, c.heading_deg) for c in cams] == [("drivebc:900", 180), (cams[1].id, 45)]
    assert cams[0].url == "https://www.drivebc.ca/images/900.jpg"


async def test_nsw_direction_with_dashes() -> None:
    cams = await NswTrafficCamFetcher(StubHttp(load("nsw_cameras.json"))).fetch(CameraQuery())
    assert [c.heading_deg for c in cams] == [270, 45]
    assert cams[0].url.startswith("https://webcams.transport.nsw.gov.au/")


async def test_deldot_live_streams_and_travel_direction() -> None:
    cams = await DelDotCameraFetcher(StubHttp(load("deldot_cameras.json"))).fetch(CameraQuery())
    assert len(cams) == 2  # the unavailable one is dropped
    assert all(c.feed is FeedKind.HLS and c.url.endswith("playlist.m3u8") for c in cams)
    assert cams[0].heading_deg is None  # "(NORTH OFF)" is a ramp, not a stated facing
    assert cams[1].heading_deg == 180  # "US 13 SB"


async def test_foreign_media_hosts_and_bad_payloads_are_refused() -> None:
    payload = load("nsw_cameras.json")
    payload["features"][0]["properties"]["href"] = "https://evil.example/x.jpeg"
    cams = await NswTrafficCamFetcher(StubHttp(payload)).fetch(CameraQuery())
    assert len(cams) == 1
    deldot = load("deldot_cameras.json")
    deldot["videoCameras"][1]["urls"]["m3u8s"] = (
        "https://video.deldot.gov.evil/live/x/playlist.m3u8"
    )
    assert len(await DelDotCameraFetcher(StubHttp(deldot)).fetch(CameraQuery())) == 1
    with pytest.raises(ProviderResponseError):
        await TflJamCamFetcher(StubHttp({"nope": 1})).fetch(CameraQuery())
    with pytest.raises(ProviderResponseError):
        await DelDotCameraFetcher(StubHttp([])).fetch(CameraQuery())
