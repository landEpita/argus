import pytest

from argus.domain.cameras import facing_from_field, facing_from_title


@pytest.mark.parametrize(
    ("value", "heading"),
    [
        ("S", 180), ("N-E", 45), ("nw", 315), ("West Facing (Home)", 270),
        ("Facing East (Home)", 90), ("North", 0), ("North East", 45), ("South West view", 225),
        ("Home", None), ("Northern Region", None), ("", None), (None, None), (3, None),
    ],
)  # fmt: skip
def test_facing_from_a_direction_field(value: object, heading: float | None) -> None:
    assert facing_from_field(value) == heading


@pytest.mark.parametrize(
    ("title", "heading"),
    [
        ("US 13 SB @ WEST DOVER CONNECTOR", 180), ("I-95 Northbound at Exit 3", 0),
        ("DE 1 @ MILFORD NECK ROAD (NORTH OFF)", None), ("5TH ST / WEST AVE", None), (None, None),
    ],
)  # fmt: skip
def test_facing_from_a_title_needs_a_travel_direction(title: object, heading: float | None) -> None:
    assert facing_from_title(title) == heading
