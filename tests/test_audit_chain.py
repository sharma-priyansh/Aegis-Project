"""Unit tests for the hash-chain primitive (ADR-014), independent of the database.

We test the pure hashing function: determinism, sensitivity to payload changes, and
that a recomputed chain detects tampering.
"""
from __future__ import annotations

from aegis_common.audit import GENESIS_HASH, _compute_hash


def _build_chain(payloads: list[dict]) -> list[tuple[int, str, str]]:
    """Return [(seq, prev_hash, hash)] for a sequence of payloads."""
    chain = []
    prev = GENESIS_HASH
    for i, p in enumerate(payloads, start=1):
        h = _compute_hash(i, prev, p)
        chain.append((i, prev, h))
        prev = h
    return chain


def test_hash_is_deterministic():
    p = {"action": "incident.opened", "service": "api"}
    assert _compute_hash(1, GENESIS_HASH, p) == _compute_hash(1, GENESIS_HASH, p)


def test_hash_sensitive_to_payload():
    h1 = _compute_hash(1, GENESIS_HASH, {"x": 1})
    h2 = _compute_hash(1, GENESIS_HASH, {"x": 2})
    assert h1 != h2


def test_hash_key_order_independent():
    h1 = _compute_hash(1, GENESIS_HASH, {"a": 1, "b": 2})
    h2 = _compute_hash(1, GENESIS_HASH, {"b": 2, "a": 1})
    assert h1 == h2


def test_chain_links_via_prev_hash():
    chain = _build_chain([{"n": 1}, {"n": 2}, {"n": 3}])
    # each record's prev_hash equals the previous record's hash
    for i in range(1, len(chain)):
        assert chain[i][1] == chain[i - 1][2]


def test_tampering_breaks_chain():
    payloads = [{"n": 1}, {"n": 2}, {"n": 3}]
    chain = _build_chain(payloads)
    # Tamper with record 2's payload and recompute its hash in isolation.
    tampered_hash = _compute_hash(2, chain[1][1], {"n": 999})
    assert tampered_hash != chain[1][2]
    # Record 3 still commits the ORIGINAL record-2 hash, so the chain no longer verifies.
    assert chain[2][1] != tampered_hash
