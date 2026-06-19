# ADR-018 — Correlation as deterministic-first stateful streaming join

**Status:** Accepted · **Date:** 2026-06-19

## Context
Correlating many signals into one incident is a cross-key, stateful streaming join that cannot be partitioned
by `incident_id` (the incident doesn't exist yet). It was under-specified and is the hardest component.

## Decision
Implement correlation as a **stateful streaming join** (Kafka Streams / Flink keyed state). **Start
deterministic**: group by topology edge + time window + signal-type rules; defer ML correlation until the
deterministic baseline is measured. **Salt/sub-key hot partitions** (hub services, large namespaces); cap
per-namespace remediation concurrency; **deterministically pre-summarize** signal storms before they reach
agent context.

## Alternatives considered
Naive per-service consumer with no shared state (cannot correlate across services); ML-first correlation
(unvalidated, opaque, premature).

## Consequences
(+) Tractable, explainable baseline; bounded agent context; no hot-partition serialization. (−) A stateful
stream processor is an added operational component.
