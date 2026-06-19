"""Console API service (FR-6.1).

Read path (CQRS-lite, AP per ADR-004): lists/inspects incidents from Postgres.
Live path: a background Kafka consumer on `incidents.lifecycle` broadcasts events to
connected WebSocket clients for a real-time timeline (NFR-1 < 1s console latency).

Control endpoints (approve/reject) are stubbed to 501 in Phase 1 and implemented in
Phase 4 with the Policy/Approval service — wiring them now would imply an action path
that does not yet exist (we do not fake business logic).
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import orjson
from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel
from sqlalchemy import select

from aegis_common.config import get_settings
from aegis_common.db import init_engine, session_scope
from aegis_common.events import Topic
from aegis_common.logging import configure_logging, get_logger
from aegis_common.models import IncidentRow, SignalRow
from aegis_common.repository import get_incident, list_incidents
from aegis_common.telemetry import setup_telemetry

log = get_logger(__name__)
settings = get_settings()


class Broadcaster:
    """Tracks connected WebSocket clients and pushes events to all of them."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._clients:
                try:
                    await ws.send_json(message)
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)


broadcaster = Broadcaster()
_consumer_task: Optional[asyncio.Task] = None


async def _live_consumer() -> None:
    """Consume lifecycle events with a unique group so every console sees all events."""
    consumer = AIOKafkaConsumer(
        Topic.INCIDENTS_LIFECYCLE.value,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=f"console-{uuid.uuid4().hex[:8]}",
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    await consumer.start()
    log.info("console live consumer started")
    try:
        async for record in consumer:
            try:
                await broadcaster.broadcast(orjson.loads(record.value))
            except Exception:  # noqa: BLE001
                log.exception("broadcast failed")
    finally:
        await consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_task
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    init_engine(settings)
    _consumer_task = asyncio.create_task(_live_consumer())
    log.info("console api ready")
    yield
    if _consumer_task:
        _consumer_task.cancel()


app = FastAPI(title="Aegis Console API", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


class SignalOut(BaseModel):
    signal_id: uuid.UUID
    kind: str
    service: str
    title: str
    severity: str

    @classmethod
    def of(cls, r: SignalRow) -> "SignalOut":
        return cls(signal_id=r.id, kind=r.kind, service=r.service, title=r.title, severity=r.severity)


class IncidentOut(BaseModel):
    incident_id: uuid.UUID
    status: str
    severity: str
    title: str
    services: list[str]
    version: int

    @classmethod
    def of(cls, r: IncidentRow) -> "IncidentOut":
        return cls(incident_id=r.id, status=r.status, severity=r.severity, title=r.title,
                   services=r.services or [], version=r.version)


class IncidentDetail(IncidentOut):
    signals: list[SignalOut] = []


@app.get("/incidents", response_model=list[IncidentOut])
async def get_incidents(status: Optional[str] = None, limit: int = 100) -> list[IncidentOut]:
    async with session_scope() as session:
        rows = await list_incidents(session, status=status, limit=limit)
        return [IncidentOut.of(r) for r in rows]


@app.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_one(incident_id: uuid.UUID) -> IncidentDetail:
    async with session_scope() as session:
        row = await get_incident(session, incident_id)
        if row is None:
            raise HTTPException(status_code=404, detail="incident not found")
        sigs = (await session.execute(
            select(SignalRow).where(SignalRow.incident_id == incident_id)
        )).scalars().all()
        detail = IncidentDetail.of(row)
        detail.signals = [SignalOut.of(s) for s in sigs]
        return detail


@app.post("/incidents/{incident_id}/approve", status_code=501)
async def approve(incident_id: uuid.UUID) -> dict:
    """Approval gate — implemented in Phase 4 with the Policy/Approval service (ADR-007)."""
    raise HTTPException(status_code=501, detail="approval gate lands in Phase 4")


@app.websocket("/ws/incidents")
async def ws_incidents(ws: WebSocket) -> None:
    await broadcaster.register(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive; ignore client messages
    except WebSocketDisconnect:
        await broadcaster.unregister(ws)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    uvicorn.run("aegis_services.console_api.app:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "8002")), log_config=None)


if __name__ == "__main__":
    main()
