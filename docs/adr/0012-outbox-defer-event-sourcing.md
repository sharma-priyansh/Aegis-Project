# ADR-012 — Transactional outbox; defer event-sourcing/CQRS

**Status:** Amended by design review · **Date:** 2026-06-19

## Context
v1.0 proposed full event-sourcing + CQRS for incident state. Incidents are not a high-frequency ledger;
the complexity/value ratio is poor early.

## Decision
Keep the **transactional outbox** (atomic DB-write + Kafka publish, prevents lost/phantom events). Model
incident state as a **checkpointed state machine + append-only hash-chained audit** (ADR-014). **Defer**
event-sourcing and CQRS read-projections until read-scale or replay requirements demand them.

## Alternatives considered
Full event-sourcing/CQRS from day one (overengineered, ADR-O1); naive dual-write (lost-event risk).

## Consequences
(+) Lower complexity and cost now; outbox preserves event integrity. (−) If heavy read-scale/temporal queries
arrive later, CQRS must be retrofitted — accepted as a deliberate YAGNI deferral.
