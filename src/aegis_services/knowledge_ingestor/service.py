"""Knowledge Ingestor (FR-4.1, FR-4.3, ADR-018 closed loop).

Two ingestion paths:
  * Runbooks/docs   — `ingest_runbook()` chunks, embeds, and upserts into Qdrant.
  * Episodic memory — consumes `incidents.lifecycle` RESOLVED events and embeds the
    resolved incident (symptoms + resolution) into `incidents_episodic`, so every closed
    incident becomes retrievable "have we seen this?" memory within minutes.

It also exposes a tiny FastAPI surface for operators/CLI to push runbooks.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from aegis_common.chunking import chunk_markdown
from aegis_common.config import get_settings
from aegis_common.embeddings import Embedder, get_embedder
from aegis_common.events import IncidentEvent, IncidentEventType, Topic
from aegis_common.kafka import InboundMessage, KafkaBus
from aegis_common.logging import configure_logging, get_logger
from aegis_common.telemetry import setup_telemetry, tracer
from aegis_common.vectorstore import Collection, VectorStore

log = get_logger(__name__)
settings = get_settings()

_embedder: Optional[Embedder] = None
_store: Optional[VectorStore] = None
_bus: Optional[KafkaBus] = None


async def _startup() -> None:
    global _embedder, _store, _bus
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    _embedder = get_embedder(settings)
    _store = VectorStore(settings, dim=_embedder.dim)
    await _store.ensure_collections()
    _bus = KafkaBus(settings)
    await _bus.start_producer()
    log.info("knowledge ingestor ready", extra={"embedder": _embedder.name, "dim": _embedder.dim})


async def ingest_runbook(*, source: str, service: str, system: str, text: str,
                         tags: Optional[list[str]] = None) -> int:
    """Chunk, embed, and upsert a runbook. Returns the number of chunks stored."""
    assert _embedder is not None and _store is not None
    chunks = chunk_markdown(text)
    if not chunks:
        return 0
    vectors = _embedder.embed([c.text for c in chunks])
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{c.ordinal}")) for c in chunks]
    payloads = [
        {"text": c.text, "source": source, "service": service, "system": system,
         "heading": c.heading, "tags": tags or []}
        for c in chunks
    ]
    await _store.upsert(Collection.RUNBOOKS, ids, vectors, payloads)
    log.info("runbook ingested", extra={"source": source, "chunks": len(chunks)})
    return len(chunks)


async def ingest_resolved_incident(event: IncidentEvent) -> None:
    """Embed a resolved incident into episodic memory (FR-4.3)."""
    assert _embedder is not None and _store is not None
    data = event.data
    text = (
        f"Incident: {data.get('title', '')}\n"
        f"Services: {', '.join(data.get('services', []))}\n"
        f"Root cause: {data.get('root_cause', 'n/a')}\n"
        f"Resolution: {data.get('resolution', 'n/a')}"
    )
    vector = _embedder.embed([text])[0]
    payload = {
        "text": text,
        "source": f"incident:{event.incident_id}",
        "service": (data.get("services") or ["unknown"])[0],
        "services": data.get("services", []),
        "severity": data.get("severity", "unknown"),
        "root_cause_class": data.get("root_cause_class", "unknown"),
        "resolved_at": event.occurred_at,
    }
    await _store.upsert(Collection.EPISODIC, [str(event.incident_id)], [vector], [payload])
    log.info("episodic incident embedded", extra={"incident_id": str(event.incident_id)})


async def _consume_resolved(msg: InboundMessage) -> None:
    event = IncidentEvent.model_validate(msg.value)
    if event.event_type == IncidentEventType.RESOLVED:
        with tracer(__name__).start_as_current_span("ingest.episodic"):
            await ingest_resolved_incident(event)


# --- API surface (operators push runbooks; consumer runs in the background) ------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    await _startup()
    assert _bus is not None
    stop = asyncio.Event()
    task = asyncio.create_task(
        _bus.consume([Topic.INCIDENTS_LIFECYCLE], "knowledge-ingestor", _consume_resolved, stop)
    )
    yield
    stop.set()
    task.cancel()
    if _store:
        await _store.close()
    if _bus:
        await _bus.stop()


app = FastAPI(title="Aegis Knowledge Ingestor", version="0.1.0", lifespan=lifespan)


class RunbookIn(BaseModel):
    source: str
    service: str
    system: str = "generic"
    text: str
    tags: list[str] = []


class IngestResult(BaseModel):
    chunks: int


@app.post("/v1/runbooks", response_model=IngestResult)
async def post_runbook(rb: RunbookIn) -> IngestResult:
    n = await ingest_runbook(source=rb.source, service=rb.service, system=rb.system,
                             text=rb.text, tags=rb.tags)
    return IngestResult(chunks=n)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    import uvicorn

    uvicorn.run("aegis_services.knowledge_ingestor.service:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "8003")), log_config=None)


if __name__ == "__main__":
    main()
