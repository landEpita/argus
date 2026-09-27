import json

import pytest

from argus import openapi


def test_dump_is_deterministic_and_complete(capsys: pytest.CaptureFixture[str]) -> None:
    openapi.main()
    first = capsys.readouterr().out
    openapi.main()
    assert capsys.readouterr().out == first

    schema = json.loads(first)
    assert {"/api/v1/aviation/aircraft", "/api/v1/watchlists", "/api/v1/preferences"} <= set(
        schema["paths"]
    )
    assert "/metrics" not in schema["paths"]
    assert "Aircraft" in schema["components"]["schemas"]
