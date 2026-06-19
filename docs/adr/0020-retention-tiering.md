# ADR-020 — Signal/trace retention tiering

**Status:** Accepted · **Date:** 2026-06-19

## Context
Ingesting ≥100k signals/min and retaining raw traces is a dominant storage/egress cost and a write-load source.

## Decision
Tier retention: short hot TTL in Kafka for active correlation; sample and roll cold data to object storage;
keep only incident-linked signals at full fidelity. Right-size backends and allow swapping to managed offerings;
gate hybrid search/re-ranking on measured retrieval gain.

## Alternatives considered
Retain everything at full fidelity (cost-prohibitive); retain nothing beyond the window (loses postmortem/replay
data).

## Consequences
(+) Bounded storage cost; incident-relevant fidelity preserved. (−) Cold data has higher access latency; sampling
policy must be tuned so it doesn't drop signals needed for replay/eval.
