"""Resilient HTTP client for a customer system.

Three failure modes are handled explicitly, because each of them has burned a
real integration:

* **transient** (timeout, 429, 5xx) — bounded retries with exponential backoff
  and the *same* `Idempotency-Key`, so a retried order is not created twice;
* **persistent** — the circuit breaker stops the traffic instead of retrying a
  dead endpoint;
* **client errors** (4xx) — never retried: the request itself is wrong, and the
  dependency is alive, so the breaker registers a success.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx

from wms_integration.circuit import CircuitBreaker, CircuitOpenError

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class HttpRequestError(RuntimeError):
    def __init__(self, *, status_code: int | None, attempts: int, detail: str) -> None:
        self.status_code = status_code
        self.attempts = attempts
        self.detail = detail
        super().__init__(f"request failed after {attempts} attempt(s): {detail}")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.1
    max_delay_seconds: float = 2.0
    jitter_ratio: float = 0.2
    retry_statuses: frozenset[int] = RETRYABLE_STATUSES

    def delay(self, attempt: int, *, rng: random.Random | None = None) -> float:
        raw = min(self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds)
        if self.jitter_ratio <= 0:
            return raw
        generator = rng or random
        return max(0.0, raw + generator.uniform(-raw * self.jitter_ratio, raw * self.jitter_ratio))


@dataclass(frozen=True)
class HttpResult:
    status_code: int
    json_body: dict[str, Any] | None
    attempts: int


@dataclass
class ResilientHttpClient:
    base_url: str
    timeout_seconds: float = 5.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    breaker: CircuitBreaker = field(
        default_factory=lambda: CircuitBreaker(failure_threshold=5, reset_timeout=timedelta(seconds=30))
    )
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient | None = None

    def __post_init__(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout_seconds, transport=self.transport
            )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> HttpResult:
        if not self.breaker.allow():
            raise CircuitOpenError(self.breaker.retry_after_seconds())

        request_headers = dict(headers or {})
        if idempotency_key:
            request_headers.setdefault("Idempotency-Key", idempotency_key)

        last_error: str = "unknown error"
        for attempt in range(1, self.retry.max_attempts + 1):
            assert self._client is not None
            try:
                response = await self._client.request(
                    method, path, json=json, headers=request_headers or None
                )
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retry.max_attempts:
                    await self.sleep(self.retry.delay(attempt))
                    continue
                self.breaker.record_failure()
                raise HttpRequestError(
                    status_code=None, attempts=attempt, detail=last_error
                ) from exc

            if response.status_code in self.retry.retry_statuses:
                last_error = f"HTTP {response.status_code}"
                if attempt < self.retry.max_attempts:
                    await self.sleep(self.retry.delay(attempt))
                    continue
                self.breaker.record_failure()
                raise HttpRequestError(
                    status_code=response.status_code, attempts=attempt, detail=last_error
                )

            if response.status_code >= 500:
                self.breaker.record_failure()
                raise HttpRequestError(
                    status_code=response.status_code,
                    attempts=attempt,
                    detail=f"HTTP {response.status_code}",
                )

            self.breaker.record_success()
            if response.status_code >= 400:
                raise HttpRequestError(
                    status_code=response.status_code,
                    attempts=attempt,
                    detail=f"HTTP {response.status_code}: {response.text[:200]}",
                )
            return HttpResult(
                status_code=response.status_code,
                json_body=_safe_json(response),
                attempts=attempt,
            )

        raise HttpRequestError(status_code=None, attempts=self.retry.max_attempts, detail=last_error)

    async def get_json(self, path: str, **kwargs: Any) -> HttpResult:
        return await self.request("GET", path, **kwargs)

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> HttpResult:
        return await self.request("POST", path, json=payload, idempotency_key=idempotency_key)


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None
