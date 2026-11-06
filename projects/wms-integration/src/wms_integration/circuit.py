"""Circuit breaker for calls to a customer system.

A WMS that answers 500 to every request must not be hammered: retries amplify
the outage and burn the integration's rate limit. The breaker opens after N
consecutive failures, stays open for a cooling-off period, then lets a single
probe through (half-open) before trusting the dependency again.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"circuit is open, retry in {retry_after:.1f}s")


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout: timedelta = timedelta(seconds=30)
    half_open_probes: int = 1
    clock: Callable[[], datetime] = utcnow
    _failures: int = field(default=0, init=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _opened_at: datetime | None = field(default=None, init=False)
    _probes: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and self._opened_at is not None:
            if self.clock() - self._opened_at >= self.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                self._probes = 0
        return self._state

    @property
    def failures(self) -> int:
        return self._failures

    def allow(self) -> bool:
        state = self.state
        if state is CircuitState.CLOSED:
            return True
        if state is CircuitState.OPEN:
            return False
        if self._probes >= self.half_open_probes:
            return False
        self._probes += 1
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._probes = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._probes = max(0, self._probes - 1)
        self._failures += 1
        if self.state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self.clock()

    def retry_after_seconds(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = (self.clock() - self._opened_at).total_seconds()
        return max(0.0, self.reset_timeout.total_seconds() - elapsed)

    def snapshot(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "failures": self._failures,
            "retry_after_seconds": round(self.retry_after_seconds(), 1),
        }
