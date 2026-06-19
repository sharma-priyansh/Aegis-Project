# ADR-005 — At-least-once delivery + idempotency over exactly-once

**Status:** Accepted · **Date:** 2026-06-19

## Context
Distributed messaging cannot cheaply guarantee exactly-once end-to-end; redelivery and duplicates are normal.

## Decision
Use at-least-once delivery with idempotent consumers. Every command carries an idempotency key; the Action
Executor keeps a unique ledger `(incident_id, step_id, idempotency_key)` so redelivered actions are no-ops.

## Alternatives considered
Exactly-once semantics (fragile, partial, costly across heterogeneous systems).

## Consequences
(+) Robust, simple, achievable; effective once-only *effects*. (−) Every handler must be designed idempotent —
a discipline, not a default.
