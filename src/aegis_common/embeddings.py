"""Embedding abstraction (ADR-010, and new ADR-021 infra-adapter pattern).

Three interchangeable backends behind one `Embedder` protocol so the model is swappable
and local/offline dev works without a model server:
  * FastEmbedEmbedder  — local ONNX model (default), no server needed.
  * OllamaEmbedder     — calls an Ollama server (AEGIS_EMBEDDING_MODEL).
  * HashingEmbedder    — deterministic, dependency-free fallback for tests/offline CI.
                         NOT for production retrieval quality; selected only when neither
                         backend is available, and it logs a clear warning.

`get_embedder()` picks the best available backend. The vector dimension is fixed per
backend and recorded so the Qdrant collection is created to match.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable

from .config import Settings
from .logging import get_logger

log = get_logger(__name__)


@runtime_checkable
class Embedder(Protocol):
    dim: int
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic bag-of-hashed-tokens embedding (offline fallback only).

    Produces a fixed-dimension L2-normalised vector from token hashes. It captures lexical
    overlap (good enough to exercise the pipeline and tests) but lacks semantic quality;
    real deployments use FastEmbed or Ollama.
    """

    name = "hashing-fallback"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in _tokenize(text):
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                vec[h % self.dim] += 1.0
            vectors.append(_l2_normalize(vec))
        return vectors


class FastEmbedEmbedder:
    name = "fastembed"

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding  # imported lazily; part of [ai] extra

        self._model = TextEmbedding(model_name=model_name)
        self.dim = 384  # bge-small-en-v1.5 dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


class OllamaEmbedder:
    name = "ollama"

    def __init__(self, base_url: str, model: str, dim: int = 768) -> None:
        import httpx

        self._client = httpx.Client(base_url=base_url, timeout=30.0)
        self._model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            resp = self._client.post("/api/embeddings", json={"model": self._model, "prompt": text})
            resp.raise_for_status()
            out.append(resp.json()["embedding"])
        return out


def get_embedder(settings: Settings) -> Embedder:
    """Select the best available embedding backend."""
    try:
        emb = FastEmbedEmbedder()
        log.info("using FastEmbed embedder", extra={"dim": emb.dim})
        return emb
    except Exception as exc:  # noqa: BLE001 - fastembed not installed or model unavailable
        log.warning("fastembed unavailable, falling back", extra={"error": str(exc)})
    try:
        emb = OllamaEmbedder(settings.ollama_url, settings.embedding_model)
        # Probe with a trivial embed to confirm the server responds.
        emb.embed(["healthcheck"])
        log.info("using Ollama embedder", extra={"model": settings.embedding_model})
        return emb
    except Exception as exc:  # noqa: BLE001
        log.warning("ollama embedder unavailable; using hashing fallback (NOT for prod)",
                    extra={"error": str(exc)})
    return HashingEmbedder()


def _tokenize(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
