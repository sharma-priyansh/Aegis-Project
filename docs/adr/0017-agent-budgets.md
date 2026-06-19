# ADR-017 — Per-incident agent budgets + circuit breakers

**Status:** Accepted · **Date:** 2026-06-19

## Context
Diagnose→Plan→Execute→Verify can loop indefinitely, and multi-agent × multi-query × escalation can stack
unbounded cost.

## Decision
Enforce hard per-incident budgets: max diagnose↔verify iterations, wall-clock deadline, and token/$ ceiling,
plus circuit breakers on the LLM/router. On exhaustion, escalate to a human with the partial findings.

## Alternatives considered
Unbounded agent loops with only soft guidance (cost and infra-thrash risk).

## Consequences
(+) Bounded cost and bounded infra impact; graceful human handoff. (−) Some hard incidents are handed off
before resolution — the safe outcome.
