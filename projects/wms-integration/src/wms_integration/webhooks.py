"""Inbound webhooks from the customer WMS.

A webhook endpoint is an unauthenticated write path, so it is guarded on three
levels: HMAC signature over `timestamp.body`, a timestamp tolerance window, and
replay protection on the signature itself. A valid signature with a stale or
reused timestamp is rejected — otherwise an attacker replays a captured call.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class SignatureError(ValueError):
    pass


class ReplayError(SignatureError):
    pass


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@dataclass
class WebhookVerifier:
    secret: str
    tolerance: timedelta = timedelta(minutes=5)
    clock: Callable[[], datetime] = utcnow
    max_seen: int = 10_000
    _seen: dict[str, datetime] = field(default_factory=dict, init=False)

    def verify(self, *, timestamp: str | None, signature: str | None, body: bytes) -> None:
        if not timestamp or not signature:
            raise SignatureError("missing X-WMS-Timestamp or X-WMS-Signature header")
        try:
            sent_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
        except (ValueError, OverflowError, OSError) as exc:
            raise SignatureError("timestamp is not a unix time in seconds") from exc

        now = self.clock()
        if sent_at - now > self.tolerance:
            raise SignatureError("timestamp is in the future")
        if now - sent_at > self.tolerance:
            raise SignatureError("timestamp is outside the tolerance window")

        expected = compute_signature(self.secret, timestamp, body)
        if not hmac.compare_digest(expected, signature):
            raise SignatureError("signature mismatch")

        self._prune(now)
        if signature in self._seen:
            raise ReplayError("duplicate delivery")
        self._seen[signature] = now

    def _prune(self, now: datetime) -> None:
        if len(self._seen) < self.max_seen:
            return
        horizon = now - self.tolerance * 2
        for signature, seen_at in list(self._seen.items()):
            if seen_at < horizon:
                self._seen.pop(signature, None)


WebhookHandler = Callable[[dict[str, Any]], Awaitable[None]]


def create_app(
    verifier: WebhookVerifier,
    handler: WebhookHandler | None = None,
) -> FastAPI:
    app = FastAPI(title="WMS Webhooks", version="0.1.0")
    app.state.verifier = verifier
    app.state.handler = handler

    @app.exception_handler(ReplayError)
    async def _replay(_request: Request, exc: ReplayError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(SignatureError)
    async def _bad_signature(_request: Request, exc: SignatureError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)})

    @app.post("/webhooks/wms/order", status_code=status.HTTP_202_ACCEPTED)
    async def receive_order(request: Request) -> dict[str, Any]:
        body = await request.body()
        verifier.verify(
            timestamp=request.headers.get("X-WMS-Timestamp"),
            signature=request.headers.get("X-WMS-Signature"),
            body=body,
        )
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="body is not valid json"
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="payload must be an object"
            )
        if app.state.handler is not None:
            await app.state.handler(payload)
        return {"accepted": True}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
