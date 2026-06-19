# ADR-002 — Kafka as the event backbone

**Status:** Accepted · **Date:** 2026-06-19

## Context
High-volume telemetry/alert ingestion and loosely-coupled services need a durable, replayable, ordered
integration substrate.

## Decision
Use Kafka as the system-of-record for events and the integration backbone (topics per lifecycle stage,
partitioned by domain key).

## Alternatives considered
RabbitMQ / NATS (weaker replay/ordering-at-scale), cloud-native queues (SQS/PubSub — vendor lock-in,
weaker ordering guarantees), direct service-to-service calls (tight coupling).

## Consequences
(+) Partitioned ordering, replay, backpressure, mature ecosystem; ordering+locality without global
coordination. (−) Operational heft; partition-key design becomes a first-class concern (see ADR-009/018).
