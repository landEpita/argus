from argus.domain.grounding import numbers_in, ungrounded


def test_numbers_are_normalised() -> None:
    assert numbers_in("Brent −8.59 % at 97.44, 4 321 oz, +2.1") == ["-8.59", "97.44", "4321", "2.1"]
    assert numbers_in("v2.0 and 3rd") == ["3"]


def test_every_figure_must_come_from_the_evidence() -> None:
    evidence = ['{"price": 97.44000244, "change_pct": -8.59, "ships": 4321}']
    assert ungrounded("Brent fell 8.59 % to 97.44; 4 321 ships.", evidence) == []
    assert ungrounded("Brent is near 97.", evidence) == []  # rounding of 97.44
    assert ungrounded("Brent fell 9.1 % to 95.", evidence) == ["9.1", "95"]


def test_small_counts_and_years_are_prose() -> None:
    assert ungrounded("Two sources, 3 events in 2026.", []) == []
    assert ungrounded("0.5 % more", []) == ["0.5"]
