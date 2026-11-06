from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class StructuredLogger(logging.Logger):
    """Logger that accepts arbitrary keyword fields.

    `logger.info("task dispatched", task_id=..., robot=...)` is valid here: the
    fields end up in `record.fields` and are rendered by the formatters below.
    Standard `logging` would reject unknown keyword arguments.
    """

    def _log(  # type: ignore[override]
        self,
        level: int,
        msg: object,
        args: tuple[Any, ...],
        exc_info: Any = None,
        extra: dict[str, Any] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        **fields: Any,
    ) -> None:
        payload: dict[str, Any] = dict(extra or {})
        if fields:
            payload["fields"] = {**payload.get("fields", {}), **fields}
        super()._log(
            level,
            msg,
            args,
            exc_info=exc_info,
            extra=payload or None,
            stack_info=stack_info,
            stacklevel=stacklevel,
        )


logging.setLoggerClass(StructuredLogger)

_BASE_RECORD_KEYS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "asctime",
    "message",
    "taskName",
    "fields",
}


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    fields: dict[str, Any] = dict(getattr(record, "fields", {}) or {})
    for key, value in record.__dict__.items():
        if key not in _BASE_RECORD_KEYS and not key.startswith("_"):
            fields[key] = value
    return fields


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update(_fields(record))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = _fields(record)
        timestamp = self.formatTime(record, "%H:%M:%S")
        base = f"{timestamp} {record.levelname:<7} {record.name}: {record.getMessage()}"
        if fields:
            base += " " + " ".join(f"{key}={value}" for key, value in fields.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for noisy in ("aiormq", "aio_pika", "asyncio", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))


def get_logger(name: str) -> StructuredLogger:
    return logging.getLogger(f"robot_dispatch.{name}")  # type: ignore[return-value]
