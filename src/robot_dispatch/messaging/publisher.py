from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Publisher(Protocol):
    """Minimal publishing contract, implemented by the real broker and by test doubles."""

    async def publish(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        message_id: str | None = None,
        headers: dict[str, Any] | None = None,
        expiration_ms: int | None = None,
    ) -> None: ...


class RecordingPublisher:
    """Collects published messages instead of sending them. Used by tests and local demos."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        self.fail_with: Exception | None = None

    async def publish(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        message_id: str | None = None,
        headers: dict[str, Any] | None = None,
        expiration_ms: int | None = None,
    ) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.published.append(
            {
                "exchange": exchange,
                "routing_key": routing_key,
                "payload": payload,
                "message_id": message_id,
                "headers": headers or {},
                "expiration_ms": expiration_ms,
            }
        )

    @property
    def count(self) -> int:
        return len(self.published)

    def clear(self) -> None:
        self.published.clear()
