"""Unit tests for RAG retrieval + precedent gate (ADR-016) with a fake vector store."""
import pytest
from aegis_common.vectorstore import Collection, RetrievedChunk
from aegis_services.rag_service.retrieval import Retriever, precedent_gate, PRECEDENT_THRESHOLD


class FakeStore:
    def __init__(self, runbooks, episodic):
        self._rb = runbooks
        self._ep = episodic

    async def search(self, collection, vector, *, limit=5, service=None, extra_filter=None):
        return (self._rb if collection == Collection.RUNBOOKS else self._ep)[:limit]


def _chunk(cid, score, text="t", **payload):
    return RetrievedChunk(id=cid, score=score, text=text, payload={"source": "s", **payload})


@pytest.mark.asyncio
async def test_retrieve_returns_both_collections():
    store = FakeStore([_chunk("r1", 0.9)], [_chunk("e1", 0.8)])
    r = Retriever(store, embed=lambda texts: [[0.0, 1.0]])
    bundle = await r.retrieve("db pool exhausted", service="api")
    assert bundle.runbook_hits and bundle.episodic_hits
    assert bundle.citations


@pytest.mark.asyncio
async def test_precedent_gate_true_above_threshold():
    store = FakeStore([], [_chunk("e1", PRECEDENT_THRESHOLD + 0.05)])
    r = Retriever(store, embed=lambda texts: [[1.0]])
    bundle = await r.retrieve("q")
    assert precedent_gate(bundle) is True


@pytest.mark.asyncio
async def test_precedent_gate_false_below_threshold():
    store = FakeStore([], [_chunk("e1", PRECEDENT_THRESHOLD - 0.1)])
    r = Retriever(store, embed=lambda texts: [[1.0]])
    bundle = await r.retrieve("q")
    assert precedent_gate(bundle) is False


@pytest.mark.asyncio
async def test_episodic_sorted_by_score():
    store = FakeStore([], [_chunk("low", 0.3), _chunk("high", 0.95)])
    r = Retriever(store, embed=lambda texts: [[1.0]])
    bundle = await r.retrieve("q")
    assert bundle.best_precedent().id == "high"
