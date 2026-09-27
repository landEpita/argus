import pytest
from pydantic import ValidationError

from argus.domain.geo import BoundingBox, GeoPoint


def box(w: float, s: float, e: float, n: float) -> BoundingBox:
    return BoundingBox(west=w, south=s, east=e, north=n)


class TestParse:
    def test_parses_west_south_east_north(self) -> None:
        assert BoundingBox.parse("2.0,48.5,2.8,49.1") == box(2.0, 48.5, 2.8, 49.1)

    @pytest.mark.parametrize("raw", ["", "1,2,3", "1,2,3,4,5", "a,b,c,d"])
    def test_rejects_malformed(self, raw: str) -> None:
        with pytest.raises(ValueError, match="bbox"):
            BoundingBox.parse(raw)

    def test_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            BoundingBox.parse("0,-91,1,1")


class TestValidation:
    def test_rejects_inverted_latitudes(self) -> None:
        with pytest.raises(ValidationError, match="south must be <= north"):
            box(0, 10, 1, 5)

    def test_rejects_antimeridian_boxes(self) -> None:
        with pytest.raises(ValidationError, match="antimeridian"):
            box(170, 0, -170, 10)


class TestContains:
    @pytest.mark.parametrize(
        ("lat", "lon", "expected"),
        [(48.8, 2.3, True), (48.5, 2.0, True), (49.2, 2.3, False), (48.8, 3.0, False)],
    )
    def test_contains(self, lat: float, lon: float, expected: bool) -> None:
        assert box(2.0, 48.5, 2.8, 49.1).contains(GeoPoint(lat=lat, lon=lon)) is expected


class TestGrid:
    def test_cache_key_rounds_outwards(self) -> None:
        assert box(2.34, 48.51, 2.81, 49.06).cache_key() == "2.3,48.5,2.9,49.1"

    def test_cache_key_handles_negatives(self) -> None:
        assert box(-12.34, -5.55, -1.01, -0.05).cache_key() == "-12.4,-5.6,-1.0,0.0"

    def test_nearby_viewports_share_a_key(self) -> None:
        assert (
            box(2.31, 48.52, 2.84, 49.03).cache_key() == box(2.33, 48.55, 2.88, 49.01).cache_key()
        )

    def test_expanded_box_contains_original(self) -> None:
        original = box(2.34, 48.51, 2.81, 49.06)
        grown = original.expanded_to_grid()
        assert grown.west <= original.west
        assert grown.east >= original.east
        assert grown.south <= original.south
        assert grown.north >= original.north

    def test_expanded_box_is_clamped(self) -> None:
        assert box(-180, -90, 180, 90).expanded_to_grid() == box(-180, -90, 180, 90)
