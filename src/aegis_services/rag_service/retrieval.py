"""Retrieval + precedent-gating logic (RAG §9, ADR-016). Pure orchestration over the
VectorStore so it is unit-testable with a fake store.

Key ADR-016 rule implemented here: `precedent_gate()` decides whether a retrieved past
incident is a strong enough precedent to permit autonomy. Autonomy is allowed ONLY when
a sufficiently similar past incident exists above a similarity threshold; otherwise the
caller must escalate to a human (abstention preferred over guessing).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from aegis_common.vectorstore import Collection, RetrievedChunk, VectorStore

# Minimum cosine similarity for an episodic match to count as a usable precedent (ADR-016).
PRECEDENT_THRESHOLD = 0.75


@dataclass
class EvidenceBundle:
    """Grounded context returned to the agent tier (RAG §9 step 4)."""

    query: str
    runbook_hits: list[RetrievedChunk] = field(default_factory=list)
    episodic_hits: list[RetrievedChunk] = field(default_factory=list)

    @property
    def citations(self) -> list[str]:
        return [c.citation for c in (self.runbook_hits + self.episodic_hits)]

    def best_precedent(self) -> RetrievedChunk | None:
        return self.episodic_hits[0] if self.episodic_hits else None


def precedent_gate(bundle: EvidenceBundle, threshold: float = PRECEDENT_THRESHOLD) -> bool:
    """True if a validated precedent strong enough to permit autonomy exists (ADR-016)."""
    best = bundle.best_precedent()
    return bool(best and best.score >= threshold)


class Retriever:
    def __init__(self, store: VectorStore, embed):
        self._store = store
        self._embed = embed  # callable: list[str] -> list[list[float]]

    async def retrieve(self, query: str, *, service: str | None = None,
                       k_runbooks: int = 5, k_episodic: int = 3) -> EvidenceBundle:
        """Service-scoped retrieval over both knowledge collections (RAG §9 steps 1-2)."""
        vector = self._embed([query])[0]
        runbooks = await self._store.search(
            Collection.RUNBOOKS, vector, limit=k_runbooks, service=service)
        episodic = await self._store.search(
            Collection.EPISODIC, vector, limit=k_episodic, service=service)
        # Episodic hits ranked by score so best_precedent() is the strongest match.
        episodic.sort(key=lambda c: c.score, reverse=True)
        return EvidenceBundle(query=query, runbook_hits=runbooks, episodic_hits=episodic)
