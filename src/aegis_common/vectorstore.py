"""Qdrant integration (ADR-008).

Three collections (architecture §8):
  * runbooks            — chunked operational docs.
  * incidents_episodic  — resolved incidents/postmortems ("have we seen this?").
  * architecture_docs   — service design/SLO notes.

Retrieval supports metadata pre-filtering (by service / recency) so search is scoped,
not global (RAG §9). The client is async (qdrant-client AsyncQdrantClient) and created
with the embedder's dimension so collection config always matches the vectors.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .config import Settings
from .logging import get_logger

log = get_logger(__name__)


class Collection(str, Enum):
    RUNBOOKS = "runbooks"
    EPISODIC = "incidents_episodic"
    ARCH_DOCS = "architecture_docs"


@dataclass
class RetrievedChunk:
    """A retrieval hit with a citation handle (RAG §9 step 4)."""

    id: str
    score: float
    text: str
    payload: dict[str, Any]

    @property
    def citation(self) -> str:
        src = self.payload.get("source") or self.payload.get("title") or self.collection
        return f"[{src}#{self.id[:8]}]"

    @property
    def collection(self) -> str:
        return str(self.payload.get("_collection", "?"))


class VectorStore:
    def __init__(self, settings: Settings, dim: int):
        from qdrant_client import AsyncQdrantClient

        self._client = AsyncQdrantClient(url=settings.qdrant_url)
        self._dim = dim

    async def ensure_collections(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        for coll in Collection:
            exists = await self._client.collection_exists(coll.value)
            if not exists:
                await self._client.create_collection(
                    collection_name=coll.value,
                    vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
                )
                log.info("created qdrant collection", extra={"collection": coll.value})

    async def upsert(self, collection: Collection, ids: list[str], vectors: list[list[float]],
                     payloads: list[dict[str, Any]]) -> None:
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=i, vector=v, payload={**p, "_collection": collection.value})
            for i, v, p in zip(ids, vectors, payloads)
        ]
        await self._client.upsert(collection_name=collection.value, points=points)

    async def search(self, collection: Collection, vector: list[float], *, limit: int = 5,
                     service: Optional[str] = None,
                     extra_filter: Optional[dict[str, Any]] = None) -> list[RetrievedChunk]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        conditions = []
        if service:
            conditions.append(FieldCondition(key="service", match=MatchValue(value=service)))
        for key, value in (extra_filter or {}).items():
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
        qfilter = Filter(must=conditions) if conditions else None

        hits = await self._client.search(
            collection_name=collection.value, query_vector=vector,
            query_filter=qfilter, limit=limit, with_payload=True,
        )
        return [
            RetrievedChunk(id=str(h.id), score=float(h.score),
                           text=str(h.payload.get("text", "")), payload=dict(h.payload or {}))
            for h in hits
        ]

    async def close(self) -> None:
        await self._client.close()
