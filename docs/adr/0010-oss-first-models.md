# ADR-010 — OSS/Ollama-first models + escalation router

**Status:** Accepted · **Date:** 2026-06-19

## Context
Per project standards, prefer open-source/Ollama-compatible models; control cost and avoid lock-in while
meeting RCA quality.

## Decision
Default to OSS models (embeddings, triage, summarization, routine steps) behind a model-router interface;
escalate only the hardest, low-confidence RCA to a larger model, under a per-incident budget.

## Alternatives considered
Single frontier model everywhere (cost, lock-in, no on-prem); OSS-only with no escalation (quality ceiling on
hard RCA).

## Consequences
(+) Cost control, portability, on-prem option for regulated tenants. (−) Router + multi-model ops complexity;
quality varies by tier and must be evaluated (ADR-016).
