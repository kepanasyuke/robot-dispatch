from __future__ import annotations

import io
import json
import logging

import pytest

from robot_dispatch.logging_setup import (
    JsonFormatter,
    StructuredLogger,
    TextFormatter,
    _fields,
    configure_logging,
    get_logger,
)


def capture(logger: logging.Logger, formatter: logging.Formatter) -> io.StringIO:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return stream


def test_get_logger_returns_structured_logger() -> None:
    logger = get_logger("unit")

    assert isinstance(logger, StructuredLogger)
    assert logger.name == "robot_dispatch.unit"


def test_structured_logger_accepts_fields() -> None:
    logger = get_logger("fields")
    stream = capture(logger, JsonFormatter())

    logger.info("task dispatched", task_id="t-1", attempt=2)

    payload = json.loads(stream.getvalue())
    assert payload["msg"] == "task dispatched"
    assert payload["task_id"] == "t-1"
    assert payload["attempt"] == 2
    assert payload["level"] == "INFO"
    assert payload["logger"] == "robot_dispatch.fields"


@pytest.mark.parametrize(
    ("method", "level"),
    [
        ("debug", "DEBUG"),
        ("info", "INFO"),
        ("warning", "WARNING"),
        ("error", "ERROR"),
        ("critical", "CRITICAL"),
    ],
)
def test_structured_logger_levels(method, level) -> None:
    logger = get_logger(f"level-{level}")
    stream = capture(logger, JsonFormatter())

    getattr(logger, method)("message", marker=1)

    assert json.loads(stream.getvalue())["level"] == level


def test_structured_logger_exception_keeps_traceback() -> None:
    logger = get_logger("exc")
    stream = capture(logger, JsonFormatter())

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("handler failed", task_id="t-2")

    payload = json.loads(stream.getvalue())
    assert payload["level"] == "ERROR"
    assert "ValueError: boom" in payload["exc"]


def test_json_formatter_includes_positional_args() -> None:
    record = logging.LogRecord("robot_dispatch.x", logging.INFO, __file__, 1, "task %s", ("t-3",), None)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["msg"] == "task t-3"


def test_text_formatter_renders_fields() -> None:
    record = logging.LogRecord("robot_dispatch.x", logging.WARNING, __file__, 1, "slow", (), None)
    record.fields = {"task_id": "t-4"}

    line = TextFormatter().format(record)

    assert line.endswith("robot_dispatch.x: slow task_id=t-4")
    assert "WARNING" in line


def test_text_formatter_without_fields() -> None:
    record = logging.LogRecord("robot_dispatch.x", logging.INFO, __file__, 1, "plain", (), None)

    assert TextFormatter().format(record).endswith("robot_dispatch.x: plain")


def test_text_formatter_renders_traceback() -> None:
    try:
        raise RuntimeError("bad")
    except RuntimeError:
        import sys

        record = logging.LogRecord(
            "robot_dispatch.x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    assert "RuntimeError: bad" in TextFormatter().format(record)


def test_fields_ignores_internal_attributes() -> None:
    record = logging.LogRecord("robot_dispatch.x", logging.INFO, __file__, 1, "m", (), None)
    record.custom = "value"
    record._private = "hidden"

    fields = _fields(record)

    assert fields == {"custom": "value"}


def test_fields_merges_extra_dict() -> None:
    record = logging.LogRecord("robot_dispatch.x", logging.INFO, __file__, 1, "m", (), None)
    record.fields = {"a": 1}

    assert _fields(record)["a"] == 1


@pytest.mark.parametrize("as_json", [True, False])
def test_configure_logging_installs_formatter(as_json) -> None:
    configure_logging("debug", as_json)

    root = logging.getLogger()
    handler = root.handlers[0]
    assert root.level == logging.DEBUG
    assert isinstance(handler.formatter, JsonFormatter if as_json else TextFormatter)


def test_configure_logging_quiets_noisy_loggers() -> None:
    configure_logging("INFO", True)

    for name in ("aio_pika", "asyncio", "aiormq", "uvicorn.access"):
        assert logging.getLogger(name).level >= logging.WARNING
