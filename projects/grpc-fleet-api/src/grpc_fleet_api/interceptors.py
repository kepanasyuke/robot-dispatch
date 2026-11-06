"""Server interceptors: access log and RPC metrics.

The interceptor wraps unary-unary handlers, so it works for any servicer without
touching business code. Latency and status are recorded per method — the two
numbers that actually answer "why is dispatch slow" during an incident.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field

import grpc

logger = logging.getLogger("grpc_fleet_api.access")


@dataclass
class MethodStats:
    ok: int = 0
    error: int = 0
    total_ms: float = 0.0

    @property
    def calls(self) -> int:
        return self.ok + self.error

    @property
    def avg_ms(self) -> float:
        return round(self.total_ms / self.calls, 3) if self.calls else 0.0


@dataclass
class MetricsRegistry:
    """Thread-safe per-method counters (gRPC serves on a worker pool)."""

    _methods: dict[str, MethodStats] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, method: str, *, ok: bool, duration_ms: float) -> None:
        with self._lock:
            stats = self._methods.setdefault(method, MethodStats())
            if ok:
                stats.ok += 1
            else:
                stats.error += 1
            stats.total_ms += duration_ms

    @property
    def total_calls(self) -> int:
        with self._lock:
            return sum(stats.calls for stats in self._methods.values())

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            return {
                method: {
                    "calls": stats.calls,
                    "ok": stats.ok,
                    "error": stats.error,
                    "avg_ms": stats.avg_ms,
                }
                for method, stats in sorted(self._methods.items())
            }


class ObservabilityInterceptor(grpc.ServerInterceptor):
    def __init__(
        self,
        metrics: MetricsRegistry | None = None,
        *,
        slow_call_ms: float = 500.0,
    ) -> None:
        self.metrics = metrics or MetricsRegistry()
        self._slow_call_ms = slow_call_ms

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None or handler.unary_unary is None:
            return handler

        method = _short_method(handler_call_details.method)
        inner = handler.unary_unary

        def unary_unary(request, context):
            started = time.perf_counter()
            ok = True
            try:
                return inner(request, context)
            except Exception:
                ok = False
                raise
            finally:
                duration_ms = (time.perf_counter() - started) * 1000.0
                self.metrics.record(method, ok=ok, duration_ms=duration_ms)
                if duration_ms > self._slow_call_ms:
                    logger.warning("slow rpc %s ok=%s %.1fms", method, ok, duration_ms)
                else:
                    logger.info("rpc %s ok=%s %.1fms", method, ok, duration_ms)

        return grpc.unary_unary_rpc_method_handler(
            unary_unary,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


def _short_method(full_method: str) -> str:
    """/fleet.v1.FleetService/GetRobot -> GetRobot"""
    return full_method.rsplit("/", 1)[-1]


def status_counter(metrics: MetricsRegistry) -> Counter[str]:
    """Convenience view for exporters."""
    return Counter(
        {method: int(item["calls"]) for method, item in metrics.snapshot().items()}
    )
