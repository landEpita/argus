import pytest
from pydantic import ValidationError

from argus.domain.preferences import Preferences


def test_defaults_mean_never_chosen() -> None:
    prefs = Preferences()
    assert prefs.enabled_layers is None
    assert prefs.viewport is None
    assert prefs.schema_version == 1


def test_valid_document() -> None:
    prefs = Preferences.model_validate(
        {
            "enabled_layers": ["aircraft", "sea-ice"],
            "viewport": {"center": {"lat": 1, "lon": 2}, "zoom": 5},
        }
    )
    assert prefs.enabled_layers == ("aircraft", "sea-ice")
    assert prefs.viewport is not None
    assert prefs.viewport.zoom == 5


@pytest.mark.parametrize("layer", ["Aircraft", "", "-lead", "has space", "x" * 65])
def test_layer_ids_are_constrained(layer: str) -> None:
    with pytest.raises(ValidationError):
        Preferences(enabled_layers=(layer,))


def test_zoom_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Preferences.model_validate({"viewport": {"center": {"lat": 0, "lon": 0}, "zoom": 23}})


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Preferences.model_validate({"schema_version": 2})
