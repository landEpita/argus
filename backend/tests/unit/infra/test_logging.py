import json
import logging

import pytest

from argus.infra.logging import JsonFormatter, RequestIdFilter, configure_logging, request_id_var


def record(msg: str = "hello %s", *args: object, **extra: object) -> logging.LogRecord:
    rec = logging.getLogger("argus.test").makeRecord(
        "argus.test", logging.INFO, __file__, 1, msg, args or ("world",), None, extra=extra
    )
    RequestIdFilter().filter(rec)
    return rec


def test_json_line_has_core_fields_extras_and_request_id() -> None:
    token = request_id_var.set("req-42")
    try:
        line = JsonFormatter().format(record(provider="opensky", duration_ms=12.5))
    finally:
        request_id_var.reset(token)
    payload = json.loads(line)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "argus.test"
    assert payload["request_id"] == "req-42"
    assert payload["provider"] == "opensky"
    assert payload["duration_ms"] == 12.5
    assert payload["ts"].endswith("+00:00")


def test_absent_request_id_is_omitted() -> None:
    assert "request_id" not in json.loads(JsonFormatter().format(record()))


def test_exceptions_are_included() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        rec = logging.getLogger("x").makeRecord(
            "x", logging.ERROR, __file__, 1, "failed", (), exc_info=__import__("sys").exc_info()
        )
    payload = json.loads(JsonFormatter().format(rec))
    assert "ValueError: boom" in payload["exc"]


@pytest.mark.parametrize("json_output", [True, False])
def test_configure_logging_installs_one_handler(json_output: bool) -> None:
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    try:
        configure_logging("debug", json_output=json_output)
        assert len(root.handlers) == 1
        assert root.level == logging.DEBUG
        assert isinstance(root.handlers[0].formatter, JsonFormatter) is json_output
    finally:
        root.handlers[:], level = saved
        root.setLevel(level)
