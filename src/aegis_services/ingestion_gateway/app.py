"""Ingestion Gateway service (FR-1).

Responsibilities:
  * Accept signals (native Aegis schema) and Alertmanager-style webhooks.
  * Authenticate via a static ingest token (local dev; swap for mTLS/OIDC in prod, §13).
  * Deduplicate floods via Redis (FR-1.3) before they hit the backbone.
  * Publish to `signals.raw`, partition-keyed by service for correlation locality.

It is intentionally thin and stateless (NFR-2): no DB, no business logic beyond
validation + dedup. Normalization and correlation happen downstream (ADR-013).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from aegis_common.config import get_settings
from aegis_common.events import SignalEvent, Topic
from aegis_common.kafka import KafkaBus
from aegis_common.logging import configure_logging, get_logger
from aegis_common.redis_util import close_redis, dedup_seen, get_redis
from aegis_common.schemas import Severity, Signal, SignalKind
from aegis_common.telemetry import setup_telemetry

log = get_logger(__name__)
settings = get_settings()
INGEST_TOKEN = os.getenv("AEGIS_INGEST_TOKEN", "dev-ingest-token")

_bus: Optional[KafkaBus] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bus
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    _bus = KafkaBus(settings)
    await _bus.start_producer()
    get_redis(settings)
    log.info("ingestion gateway ready")
    yield
    await _bus.stop()
    await close_redis()


app = FastAPI(title="Aegis Ingestion Gateway", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


def require_token(x_aegis_token: str = Header(default="")) -> None:
    if x_aegis_token != INGEST_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingest token")


async def _ingest(signal: Signal) -> bool:
    """Dedup + publish one signal. Returns True if accepted, False if deduplicated."""
    assert _bus is not None
    redis = get_redis(settings)
    if await dedup_seen(redis, signal.fingerprint(), settings.dedup_window_seconds):
        log.info("signal deduplicated", extra={"service": signal.service, "title": signal.title})
        return False
    span = trace.get_current_span().get_span_context()
    trace_id = format(span.trace_id, "032x") if span and span.is_valid else None
    event = SignalEvent.of(signal, trace_id=trace_id)
    await _bus.publish(Topic.SIGNALS_RAW, key=signal.service, value=event.model_dump(mode="json"))
    return True


class IngestResult(BaseModel):
    accepted: int
    deduplicated: int


@app.post("/v1/signals", response_model=IngestResult, dependencies=[Depends(require_token)])
async def ingest_signals(signals: list[Signal]) -> IngestResult:
    accepted = 0
    for sig in signals:
        if await _ingest(sig):
            accepted += 1
    return IngestResult(accepted=accepted, deduplicated=len(signals) - accepted)


# --- Alertmanager-compatible webhook ---------------------------------------------------

class AMAlert(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class AMWebhook(BaseModel):
    alerts: list[AMAlert] = []


_SEVERITY_MAP = {"critical": Severity.SEV1, "warning": Severity.SEV2, "info": Severity.SEV4}


@app.post("/v1/alerts/alertmanager", response_model=IngestResult,
          dependencies=[Depends(require_token)])
async def ingest_alertmanager(webhook: AMWebhook) -> IngestResult:
    """Map Alertmanager alerts to canonical Signals (FR-1.1)."""
    accepted = 0
    firing = [a for a in webhook.alerts if a.status == "firing"]
    for alert in firing:
        service = alert.labels.get("service") or alert.labels.get("job") or "unknown"
        signal = Signal(
            kind=SignalKind.ALERT,
            source="alertmanager",
            service=service,
            title=alert.labels.get("alertname", "alert"),
            description=alert.annotations.get("description", ""),
            severity=_SEVERITY_MAP.get(alert.labels.get("severity", ""), Severity.UNKNOWN),
            labels=alert.labels,
        )
        if await _ingest(signal):
            accepted += 1
    return IngestResult(accepted=accepted, deduplicated=len(firing) - accepted)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready" if _bus is not None else "starting"}


def main() -> None:
    import uvicorn

    uvicorn.run(
        "aegis_services.ingestion_gateway.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        log_config=None,
    )


if __name__ == "__main__":
    main()
