"""Thin MQTT source for the ingestor.

`paho-mqtt` is optional (`pip install -e ".[mqtt]"`): the ingest policies do not
depend on the transport, and tests drive `TelemetryIngestor.offer` directly.
The adapter only parses payloads and hands them to the asyncio loop.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from pydantic import ValidationError

from telemetry_hub.ingest import TelemetryIngestor
from telemetry_hub.logging import get_logger
from telemetry_hub.models import TelemetrySample

logger = get_logger("mqtt")


class TelemetrySource(Protocol):
    async def run(self, ingestor: TelemetryIngestor, stop: asyncio.Event) -> None: ...


def parse_payload(payload: bytes) -> TelemetrySample | None:
    """Parse one MQTT payload; malformed messages are logged and skipped."""
    try:
        raw: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.warning("telemetry payload is not json: %s (%d bytes)", exc, len(payload))
        return None
    try:
        return TelemetrySample.model_validate(raw)
    except ValidationError as exc:
        logger.warning("telemetry payload is invalid: %d errors", exc.error_count())
        return None


class PahoMqttSource:
    """Bridges paho callbacks (thread) into the asyncio ingestor queue."""

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 1883,
        topic: str = "fleet/+/telemetry",
        qos: int = 1,
        client_id: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._topic = topic
        self._qos = qos
        self._client_id = client_id
        self._username = username
        self._password = password

    async def run(self, ingestor: TelemetryIngestor, stop: asyncio.Event) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError('paho-mqtt is not installed: pip install ".[mqtt]"') from exc

        loop = asyncio.get_running_loop()
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id, protocol=mqtt.MQTTv311
        )
        if self._username:
            client.username_pw_set(self._username, self._password)

        def on_message(_client: Any, _userdata: Any, message: Any) -> None:
            sample = parse_payload(message.payload)
            if sample is not None:
                asyncio.run_coroutine_threadsafe(ingestor.offer(sample), loop)

        def on_connect(_client: Any, _userdata: Any, _flags: Any, reason_code: Any, _props: Any) -> None:
            logger.info("mqtt connected: %s", reason_code)
            client.subscribe(self._topic, qos=self._qos)

        client.on_message = on_message
        client.on_connect = on_connect
        client.connect_async(self._host, self._port)
        client.loop_start()
        logger.info("mqtt source started: %s %s", self._host, self._topic)
        try:
            await stop.wait()
        finally:
            client.loop_stop()
            client.disconnect()
            logger.info("mqtt source stopped")
