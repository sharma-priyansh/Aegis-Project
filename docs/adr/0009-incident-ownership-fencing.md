# ADR-009 — Incident ownership: Kafka partition + Postgres fencing token

**Status:** Accepted (revises the v1.0 Redis-Redlock decision) · **Date:** 2026-06-19

## Context
Exactly one orchestrator must drive each incident, and the *dangerous* path (executing remediation) must be
safe under failover and GC pauses. The v1.0 design used a Redis TTL lock (Redlock-style) as the ownership
primitive.

## Decision
Derive single-driver semantics from **Kafka single-consumer-per-partition** on `incidents.lifecycle[incident_id]`.
Guard the action path with a **monotonic fencing token issued from a Postgres sequence** (linearizable),
re-verified by the credential issuer and the Action Executor before any mutation. Redis is demoted to advisory
roles (dedup, cache) only.

## Alternatives considered
Redis Redlock (rejected: not a reliable mutual-exclusion primitive under failover — Kleppmann critique);
ZooKeeper/etcd consensus (heavier than needed given Kafka already provides single-consumer ownership);
DB advisory locks alone (no fencing against stale owners on the action path).

## Consequences
(+) Linearizable fencing on the only path that can cause harm; reuses Kafka's existing ownership guarantee;
removes a correctness dependency on Redis. (−) Fencing-token issuance adds a Postgres round-trip on the action
path (acceptable — actions are rare relative to signals).
