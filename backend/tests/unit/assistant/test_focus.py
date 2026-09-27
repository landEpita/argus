from argus.services.assistant.agent import Step
from argus.services.assistant.focus import MapFocus, focus_from


def test_the_last_place_read_and_every_layer_showing_the_data() -> None:
    steps = [
        Step("quotes", {}, True, "22 items"),
        Step("events", {"feed": "conflict", "lat": 15, "lon": 42, "radius_km": 500}, True, "3"),
        Step("military_aircraft", {"lat": 13.5, "lon": 43.2, "radius_km": 100}, True, "2"),
        Step("events", {"feed": "gossip", "lat": 1, "lon": 1}, False, "bad feed"),
    ]
    assert focus_from(steps) == MapFocus(13.5, 43.2, 7.0, None, ("conflict", "military"))


def test_a_country_when_no_point_was_read() -> None:
    steps = [Step("country", {"iso2": "ua"}, True, "5 fields")]
    assert focus_from(steps) == MapFocus(None, None, None, "UA", ("country-index",))


def test_nothing_to_show() -> None:
    assert focus_from([Step("quotes", {}, True, "22 items")]) is None
    assert focus_from([Step("events", {"feed": "conflict", "lat": 999, "lon": 0}, True, "")]) == (
        MapFocus(None, None, None, None, ("conflict",))
    )
