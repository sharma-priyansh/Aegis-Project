# ADR-006 — Externalized, checkpointed workflow state

**Status:** Accepted · **Date:** 2026-06-19

## Context
Workflows are long-running, include human-approval interrupts, and must survive pod restarts and scaling.

## Decision
Externalize all workflow state (Postgres for durable state, Redis for advisory/perf) and checkpoint the
LangGraph `IncidentState` after every node so any worker can resume any incident.

## Alternatives considered
In-memory agent state — lost on crash, not scalable, cannot survive HITL waits.

## Consequences
(+) Crash-tolerant, horizontally scalable, resumable approval interrupts. (−) Serialization overhead and
checkpoint-validation requirements (see ADR-017/AG3).
