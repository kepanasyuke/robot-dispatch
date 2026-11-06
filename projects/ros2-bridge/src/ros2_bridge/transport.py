"""Transport boundary of the bridge.

`Transport` is the only thing the bridge knows about ROS2. In production it is
backed by `rclpy`; in tests and in the `--dry-run` mode it is `FakeTransport`,
which records publishes and lets a test inject incoming messages. Keeping the
boundary this narrow is what makes the integration logic testable without a
ROS2 installation.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

MessageHandler = Callable[[str, dict[str, Any]], None]


@runtime_checkable
class Transport(Protocol):
    async def subscribe(self, topic: str, handler: MessageHandler) -> None: ...

    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...


class FakeTransport:
    """In-memory transport: records outgoing messages, injects incoming ones."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.fail_next_publish: Exception | None = None
        self._handlers: dict[str, list[MessageHandler]] = defaultdict(list)
        self._subscriptions: list[str] = []

    @property
    def subscriptions(self) -> list[str]:
        return list(self._subscriptions)

    async def subscribe(self, topic: str, handler: MessageHandler) -> None:
        self._handlers[topic].append(handler)
        self._subscriptions.append(topic)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        if self.fail_next_publish is not None:
            error, self.fail_next_publish = self.fail_next_publish, None
            raise error
        self.published.append((topic, payload))

    async def inject(self, topic: str, payload: dict[str, Any]) -> None:
        for handler in list(self._handlers.get(topic, [])):
            handler(topic, payload)

    def last_payload(self, topic: str | None = None) -> dict[str, Any]:
        for published_topic, payload in reversed(self.published):
            if topic is None or published_topic == topic:
                return payload
        raise LookupError("nothing has been published")

    async def drain(self) -> None:
        """Yield control so fire-and-forget coroutines can finish."""
        await asyncio.sleep(0)
