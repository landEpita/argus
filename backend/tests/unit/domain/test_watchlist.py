import pytest
from pydantic import ValidationError

from argus.domain.watchlist import MAX_ITEMS_PER_WATCHLIST, WatchItem, WatchKind, WatchlistDraft


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        (WatchKind.AIRCRAFT, " 3C6444 ", "3c6444"),
        (WatchKind.VESSEL, "227006760", "227006760"),
        (WatchKind.TICKER, "brk.b", "BRK.B"),
        (WatchKind.TICKER, "^gspc", "^GSPC"),
        (WatchKind.COUNTRY, "fr", "FR"),
        (WatchKind.KEYWORD, "  Strait   of Hormuz ", "Strait of Hormuz"),
    ],
)
def test_values_are_normalised_per_kind(kind: WatchKind, raw: str, expected: str) -> None:
    assert WatchItem(kind=kind, value=raw).value == expected


@pytest.mark.parametrize(
    ("kind", "raw"),
    [
        (WatchKind.AIRCRAFT, "3c644"),
        (WatchKind.AIRCRAFT, "zzzzzz"),
        (WatchKind.VESSEL, "12345"),
        (WatchKind.TICKER, "SPACE HERE"),
        (WatchKind.COUNTRY, "FRA"),
        (WatchKind.KEYWORD, "   "),
        (WatchKind.KEYWORD, "x" * 101),
    ],
)
def test_invalid_values_are_rejected(kind: WatchKind, raw: str) -> None:
    with pytest.raises(ValidationError, match="invalid"):
        WatchItem(kind=kind, value=raw)


def test_unknown_kind_reports_the_kind_error_only() -> None:
    with pytest.raises(ValidationError) as info:
        WatchItem.model_validate({"kind": "spaceship", "value": "x"})
    assert [e["loc"] for e in info.value.errors()] == [("kind",)]


def test_blank_label_becomes_none() -> None:
    assert WatchItem(kind=WatchKind.COUNTRY, value="FR", label="  ").label is None
    assert WatchItem(kind=WatchKind.COUNTRY, value="FR", label=" France ").label == "France"


class TestDraft:
    def test_name_whitespace_is_collapsed(self) -> None:
        assert WatchlistDraft(name="  Gulf   ops ").name == "Gulf ops"

    def test_blank_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            WatchlistDraft(name="   ")

    def test_duplicates_after_normalisation_are_rejected(self) -> None:
        items = (
            WatchItem(kind=WatchKind.AIRCRAFT, value="3C6444"),
            WatchItem(kind=WatchKind.AIRCRAFT, value="3c6444"),
        )
        with pytest.raises(ValidationError, match="duplicate item: aircraft:3c6444"):
            WatchlistDraft(name="x", items=items)

    def test_same_value_under_different_kinds_is_fine(self) -> None:
        items = (
            WatchItem(kind=WatchKind.TICKER, value="FR"),
            WatchItem(kind=WatchKind.COUNTRY, value="FR"),
        )
        assert len(WatchlistDraft(name="x", items=items).items) == 2

    def test_item_count_is_capped(self) -> None:
        items = tuple(
            WatchItem(kind=WatchKind.KEYWORD, value=f"k{i}")
            for i in range(MAX_ITEMS_PER_WATCHLIST + 1)
        )
        with pytest.raises(ValidationError):
            WatchlistDraft(name="x", items=items)
