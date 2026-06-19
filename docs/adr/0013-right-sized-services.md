# ADR-013 — Right-sized v1 service topology (~7 services)

**Status:** Accepted · **Date:** 2026-06-19

## Context
v1.0 specified 11 services; several share state/lifecycle and split prematurely.

## Decision
v1 topology (~7): Ingestion Gateway; Detection & Correlation (absorbs Normalizer); Incident Orchestrator
(runs agents in-process via LangGraph); RAG Service; Policy & Approval; Action Executor; Notification (absorbs
Communicator). Plus Console API and Knowledge Ingestor as supporting services. Service mesh and multi-tenancy
are deferred.

## Alternatives considered
11 fine-grained services (premature decomposition, higher ops/cost); a monolith (poor scaling/blast-radius
isolation on the action path).

## Consequences
(+) Lower operational and latency overhead; boundaries follow real state ownership. (−) Some services will be
split later as scale demands — an intentional, reversible simplification.
