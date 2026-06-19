# ADR-008 — Qdrant as the vector database

**Status:** Accepted · **Date:** 2026-06-19

## Context
RCA needs fast, filterable retrieval over runbooks and past incidents with metadata scoping and (later)
hybrid search.

## Decision
Use Qdrant (OSS, K8s-native) with payload filtering, HNSW, optional hybrid search, sharding, and replication.

## Alternatives considered
pgvector (overloads Postgres, weaker at scale/filtering), Pinecone (managed lock-in, cost), Weaviate/Milvus
(viable; Qdrant chosen for filtering ergonomics + footprint + on-prem option).

## Consequences
(+) Portable, on-prem-capable, good metadata filtering, independent scaling. (−) Another stateful backend to
operate; retrieval features should be added only as evals justify (ADR-020/O3).
