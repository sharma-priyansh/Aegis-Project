# ADR-019 — Aegis reliability isolation + no self-remediation in v1

**Status:** Accepted · **Date:** 2026-06-19

## Context
Aegis must be more reliable than the systems it watches and must never become a blocker on human incident
response. Self-monitoring risks cascading auto-remediation loops.

## Decision
Run Aegis in a **separate failure domain** from the systems it remediates; the **human paging path never
transits the AI tier**; degrade safe to deterministic detection+paging if the AI/agent tier is down. **Remove
self-remediation in v1** — Aegis is monitored by a separate, simpler external monitor.

## Alternatives considered
Co-locating Aegis with its targets (shared-fate failure); Aegis auto-remediating itself (cascading-loop risk).

## Consequences
(+) Aegis failure cannot block human response; no self-referential remediation loop. (−) A separate, simpler
monitor must exist for Aegis itself; some cross-domain infra duplication.
