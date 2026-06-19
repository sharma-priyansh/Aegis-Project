"""RAG Service API (FR-4).

Exposes retrieval to the agent tier over HTTP (gRPC-equivalent sync request/response,
Agent-comms §10). Returns grounded evidence with citation handles and a `has_precedent`
flag the orchestrator uses to gate autonomy (ADR-016).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel

from aegis_common.config import get_settings
from aegis_common.embeddings import Embedder, get_embedder
from aegis_common.logging import configure_logging, get_logger
from aegis_common.telemetry import setup_telemetry, tracer
from aegis_common.vectorstore import VectorStore

from .retrieval import Retriever, precedent_gate

log = get_logger(__name__)
settings = get_settings()

_embedder: Optional[Embedder] = None
_store: Optional[VectorStore] = None
_retriever: Optional[Retriever] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _embedder, _store, _retriever
    configure_logging(settings.log_level)
    setup_telemetry(settings)
    _embedder = get_embedder(settings)
    _store = VectorStore(settings, dim=_embedder.dim)
    await _store.ensure_collections()
    _retriever = Retriever(_store, _embedder.embed)
    log.info("rag service ready", extra={"embedder": _embedder.name})
    yield
    if _store:
        await _store.close()


app = FastAPI(title="Aegis RAG Service", version="0.1.0", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)


class RetrieveRequest(BaseModel):
    query: str
    service: Optional[str] = None
    k_runbooks: int = 5
    k_episodic: int = 3


class Hit(BaseModel):
    id: str
    score: float
    text: str
    citation: str
    source: str


class RetrieveResponse(BaseModel):
    query: str
    runbooks: list[Hit]
    episodic: list[Hit]
    citations: list[str]
    has_precedent: bool  # ADR-016 autonomy gate
    best_precedent_score: float


@app.post("/v1/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    assert _retriever is not None
    with tracer(__name__).start_as_current_span("rag.retrieve") as span:
        bundle = await _retriever.retrieve(
            req.query, service=req.service,
            k_runbooks=req.k_runbooks, k_episodic=req.k_episodic)
        best = bundle.best_precedent()
        has_precedent = precedent_gate(bundle)
        span.set_attribute("rag.has_precedent", has_precedent)
        span.set_attribute("rag.runbook_hits", len(bundle.runbook_hits))

        def to_hits(chunks) -> list[Hit]:
            return [Hit(id=c.id, score=c.score, text=c.text, citation=c.citation,
                        source=str(c.payload.get("source", ""))) for c in chunks]

        return RetrieveResponse(
            query=req.query,
            runbooks=to_hits(bundle.runbook_hits),
            episodic=to_hits(bundle.episodic_hits),
            citations=bundle.citations,
            has_precedent=has_precedent,
            best_precedent_score=best.score if best else 0.0,
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready" if _retriever is not None else "starting"}


def main() -> None:
    import uvicorn

    uvicorn.run("aegis_services.rag_service.app:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "8004")), log_config=None)


if __name__ == "__main__":
    main()
