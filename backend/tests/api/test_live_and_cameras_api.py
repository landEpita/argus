from argus.domain.cameras import CAMERAS, CameraNetwork
from argus.domain.live_video import CHANNELS, WEBCAMS
from tests.api.conftest import ClientFactory
from tests.api.test_phase2b_api import register
from tests.unit.services.test_cameras import Catalog, cam


async def test_live_catalogs(make_client: ClientFactory) -> None:
    client = await make_client()
    channels = (await client.get("/api/v1/live/channels")).json()
    assert len(channels) == len(CHANNELS)
    assert channels[0]["streams"][0]["kind"] == "youtube"
    webcams = (await client.get("/api/v1/live/webcams")).json()
    assert len(webcams) == len(WEBCAMS)
    assert webcams[-1]["position"] is None  # the ISS view has no place on the map


async def test_cameras_in_a_box(make_client: ClientFactory) -> None:
    tfl = Catalog("tfl", [cam("a", CameraNetwork.TFL, 51.5, -0.1)])
    client = await make_client(configure=register((CAMERAS[CameraNetwork.TFL], tfl)))
    body = (await client.get("/api/v1/cameras", params={"bbox": "-1,51,1,52"})).json()
    assert (body["count"], body["networks"], body["unavailable"]) == (1, ["tfl"], [])
    assert (await client.get("/api/v1/cameras", params={"bbox": "nope"})).status_code == 422
    networks = (await client.get("/api/v1/cameras/networks")).json()
    assert {n["network"] for n in networks} == {n.value for n in CameraNetwork}
