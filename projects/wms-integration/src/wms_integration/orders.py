"""Order sync: translate a WMS order into a dispatch task.

The external id is derived from the order id, so a retry of the same order is
absorbed by the dispatch service idempotency instead of creating a duplicate
delivery. Mapping is validated before the first byte goes over the wire.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from wms_integration.client import ResilientHttpClient

TASK_PATH = "/api/v1/tasks"


class OrderValidationError(ValueError):
    pass


@dataclass(frozen=True)
class WmsOrder:
    order_id: str
    destination: str
    priority: int = 100
    items: int = 1
    deadline: datetime | None = None
    comment: str | None = None


@dataclass(frozen=True)
class SyncResult:
    order_id: str
    external_id: str
    created: bool
    attempts: int
    task_id: str | None


class OrderSyncService:
    def __init__(self, client: ResilientHttpClient, *, task_type: str = "delivery") -> None:
        self._client = client
        self._task_type = task_type

    async def sync(self, order: WmsOrder) -> SyncResult:
        external_id = self.external_id(order)
        payload = self.to_task_payload(order)
        result = await self._client.post_json(
            TASK_PATH, payload, idempotency_key=external_id
        )
        body = result.json_body or {}
        return SyncResult(
            order_id=order.order_id,
            external_id=external_id,
            created=result.status_code == 201,
            attempts=result.attempts,
            task_id=body.get("id"),
        )

    @staticmethod
    def external_id(order: WmsOrder) -> str:
        return f"wms:{order.order_id}"

    def to_task_payload(self, order: WmsOrder) -> dict[str, Any]:
        if not order.order_id.strip():
            raise OrderValidationError("order_id must not be empty")
        if not order.destination.strip():
            raise OrderValidationError("destination must not be empty")
        if order.items < 1:
            raise OrderValidationError("items must be at least 1")
        if not 0 <= order.priority <= 1000:
            raise OrderValidationError("priority must be within 0..1000")

        task_payload: dict[str, Any] = {
            "destination": order.destination,
            "items": order.items,
            "wms_order_id": order.order_id,
        }
        if order.comment:
            task_payload["comment"] = order.comment
        if order.deadline is not None:
            task_payload["deadline"] = order.deadline.isoformat()

        return {
            "type": self._task_type,
            "external_id": self.external_id(order),
            "priority": order.priority,
            "payload": task_payload,
        }
