# ADR-001 — Domain = Agentic AIOps (Aegis)

**Status:** Accepted · **Date:** 2026-06-19

## Context
We need one project that authentically exercises agentic AI, multi-agent systems, LangGraph/LangChain, RAG,
vector DBs, distributed systems, event-driven architecture, microservices, Kafka, Redis, Postgres, K8s, and
OpenTelemetry — and is more impressive than a chatbot/doc-Q&A/SaaS clone.

## Decision
Build Aegis, an autonomous incident-response & remediation platform (agentic AIOps).

## Alternatives considered
Fraud-investigation co-pilot (62/70), cloud cost+reliability optimizer, supply-chain control tower, M&A
due-diligence, data-pipeline healing, prior-auth automation, grid demand-response, legal CLM, trust & safety.

## Consequences
(+) Every required technology is load-bearing, not decorative; OpenTelemetry is the domain; highest
distributed-systems depth and future demand. (−) High intrinsic complexity and a hard safety bar; the system
takes consequential production actions, raising the correctness/operational stakes.
