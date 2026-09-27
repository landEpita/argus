import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sgp4 import omm
from sgp4.api import Satrec, jday

from argus.adapters.celestrak import CelestrakElementsFetcher
from argus.domain.orbit import (
    WGS84_A_KM,
    PropagationError,
    build_satrec,
    ecef_to_geodetic,
    gmst_radians,
    propagate,
    teme_to_geodetic,
)
from argus.domain.space import ElementsQuery, OrbitalElements, SatelliteGroup
from tests.fakes import StubHttp

FIXTURE = Path(__file__).parents[2] / "fixtures" / "celestrak_stations.json"
RAW = json.loads(FIXTURE.read_text())


def iss() -> OrbitalElements:
    return CelestrakElementsFetcher(StubHttp()).transform(
        ElementsQuery(group=SatelliteGroup.STATIONS), RAW
    )[0]


def test_satrec_matches_the_reference_omm_initialisation() -> None:
    elements = iss()
    reference = Satrec()
    omm.initialize(reference, RAW[0])
    for minutes in (0, 45, 90, 600):
        at = elements.epoch + timedelta(minutes=minutes)
        jd, fr = jday(
            at.year, at.month, at.day, at.hour, at.minute, at.second + at.microsecond / 1e6
        )
        ours_err, ours_r, ours_v = build_satrec(elements).sgp4(jd, fr)
        ref_err, ref_r, ref_v = reference.sgp4(jd, fr)
        assert ours_err == ref_err == 0
        assert ours_r == pytest.approx(ref_r, abs=1e-9)
        assert ours_v == pytest.approx(ref_v, abs=1e-12)


def test_iss_is_where_the_iss_should_be() -> None:
    elements = iss()
    for hours in (0, 1, 6, 24):
        state = propagate(build_satrec(elements), elements.epoch + timedelta(hours=hours))
        assert 380 < state.geodetic.alt_km < 450
        assert abs(state.geodetic.lat_deg) <= 51.7  # its inclination bounds latitude
        assert 7.5 < state.speed_kms < 7.8


def test_gmst_known_value() -> None:
    # GMST at J2000.0 (2000-01-01 12:00 UT) is 280.46061837 degrees.
    at = datetime(2000, 1, 1, 12, tzinfo=UTC)
    assert math.degrees(gmst_radians(at)) == pytest.approx(280.46061837, abs=1e-5)


@pytest.mark.parametrize(
    ("xyz", "expected"),
    [
        ((WGS84_A_KM, 0, 0), (0, 0, 0)),
        ((0, WGS84_A_KM + 100, 0), (0, 90, 100)),
        ((0, 0, 6356.752 + 10), (90, 0, 10)),
    ],
)
def test_ecef_to_geodetic(
    xyz: tuple[float, float, float], expected: tuple[float, float, float]
) -> None:
    g = ecef_to_geodetic(*xyz)
    assert (g.lat_deg, g.lon_deg, g.alt_km) == pytest.approx(expected, abs=1e-3)


def test_teme_rotation_by_gmst() -> None:
    # At J2000.0 noon, a point on TEME +x lies at longitude -GMST.
    at = datetime(2000, 1, 1, 12, tzinfo=UTC)
    g = teme_to_geodetic((WGS84_A_KM, 0, 0), at)
    assert g.lon_deg == pytest.approx(-(280.46061837 - 360), abs=1e-4)


def test_decayed_orbit_raises() -> None:
    doomed = iss().model_copy(update={"mean_motion_rev_per_day": 17.5, "bstar": 0.5})
    with pytest.raises(PropagationError):
        propagate(build_satrec(doomed), doomed.epoch + timedelta(days=60))


class TestCelestrak:
    async def test_fetch_and_parse(self) -> None:
        http = StubHttp(RAW)
        elements = await CelestrakElementsFetcher(http, "https://ct.test/gp.php").fetch(
            ElementsQuery(group=SatelliteGroup.STATIONS)
        )
        assert http.calls == [("https://ct.test/gp.php", {"GROUP": "stations", "FORMAT": "json"})]
        assert elements[0].name == "ISS (ZARYA)"
        assert elements[0].norad_id == 25544
        assert elements[0].epoch.tzinfo is not None

    def test_text_answer_is_an_error(self) -> None:
        from argus.providers.errors import ProviderResponseError

        with pytest.raises(ProviderResponseError):
            CelestrakElementsFetcher(StubHttp()).transform(
                ElementsQuery(group=SatelliteGroup.STATIONS), "Invalid query"
            )

    def test_bad_records_are_skipped(self) -> None:
        records = [{"OBJECT_NAME": "X"}, {**RAW[0], "EPOCH": "garbage"}, RAW[1]]
        parsed = CelestrakElementsFetcher(StubHttp()).transform(
            ElementsQuery(group=SatelliteGroup.STATIONS), records
        )
        assert [e.norad_id for e in parsed] == [RAW[1]["NORAD_CAT_ID"]]
