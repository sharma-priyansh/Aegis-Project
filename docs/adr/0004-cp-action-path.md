# ADR-004 — CP (consistency) on the action path

**Status:** Accepted · **Date:** 2026-06-19

## Context
Under partition/failover, an autonomous system that mutates production must never double-remediate or act
without certainty of ownership.

## Decision
The action path is CP: if Aegis cannot confirm it holds the incident and a fresh fencing token, it refuses to
act and pages a human. The read/observability path stays AP (may serve slightly stale state).

## Alternatives considered
AP / optimistic action (act, reconcile later) — unacceptable blast-radius risk for infra mutation.

## Consequences
(+) Never acts unsafely under uncertainty. (−) During partitions some safe automation pauses and falls back to
humans — accepted trade for safety.
