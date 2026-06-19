# ADR-021 — Pluggable infra adapters with deterministic offline backends

**Status:** Accepted · **Date:** 2026-06-19

## Context
Phases 2-4 introduce three external dependencies that are heavy or unavailable in local
dev / CI: an embedding model, an LLM, and a Kubernetes cluster to remediate. We need the
full agent graph, RAG pipeline, PDP/PEP, budgets, and grounding to be runnable and testable
without any of them, while using real backends in production (ADR-010/011).

## Decision
Put each external dependency behind a small interface with two+ backends, selected at
runtime by availability:
  * Embeddings — `FastEmbedEmbedder` (local ONNX) / `OllamaEmbedder` / `HashingEmbedder` (offline fallback).
  * LLM — `OllamaLLM` / `RuleBasedLLM` (deterministic offline backend).
  * Action runtime — `KubernetesRuntime` / `DryRunRuntime`.

The offline backends are **infrastructure adapters**, not mock business logic: the agent
state machine, retrieval, gating (ADR-016), budgets (ADR-017), PDP/PEP (ADR-014), saga
rollback, and audit are identical regardless of backend. Only the model/cluster endpoint
changes. Offline backends log a clear warning and are never silently used in production.

## Alternatives considered
Hard-require Ollama + Qdrant + a cluster for any run (kills local dev/CI ergonomics);
mock the whole agent layer (would hide real logic and violate "no mock business logic").

## Consequences
(+) The platform is runnable and unit-testable end-to-end offline; production swaps in real
models/cluster via config with zero logic change. (−) The offline LLM's reasoning quality is
intentionally low; it validates control flow and safety, not RCA accuracy. Retrieval/RCA
quality must be evaluated against real models (ADR-016 replay eval) before trusting autonomy.
