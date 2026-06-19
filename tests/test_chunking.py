"""Unit tests for structure-aware chunking (RAG §8)."""
from aegis_common.chunking import chunk_markdown


def test_empty_returns_no_chunks():
    assert chunk_markdown("") == []


def test_splits_on_headings():
    text = "# A\nbody a\n## B\nbody b"
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2
    assert any("A" in c.heading for c in chunks)


def test_size_bounding_with_overlap():
    text = "# H\n" + ("x" * 2000)
    chunks = chunk_markdown(text, max_chars=500, overlap_chars=50)
    assert len(chunks) > 1
    assert all(len(c.text) <= 500 for c in chunks)
