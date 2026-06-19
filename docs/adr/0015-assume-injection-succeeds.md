# ADR-015 — Assume-injection-succeeds security model

**Status:** Accepted · **Date:** 2026-06-19

## Context
Telemetry, logs, and retrieved documents are attacker-influenceable and feed LLMs, which do not reliably
maintain a data/instruction boundary.

## Decision
Adopt the invariant that **prompt injection may succeed**, and ensure it still cannot cause harm: **no LLM
output may directly trigger an action**; the governed catalog + approval gate + fencing token are the only
action path; every action parameter is schema-validated against the catalog; agent tool egress is restricted;
secrets never enter prompts or logs.

## Alternatives considered
Relying on the LLM to resist injection / "untrusted-content" prompting alone (insufficient as a hard control).

## Consequences
(+) Security does not depend on model robustness; safe under adversarial input. (−) Requires strict
output/parameter validation and constrains how directly agents can act (by design).
