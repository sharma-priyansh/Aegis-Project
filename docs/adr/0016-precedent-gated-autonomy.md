# ADR-016 — Precedent-gated autonomy + abstention + replay eval

**Status:** Accepted · **Date:** 2026-06-19

## Context
RAG/episodic memory is strongest on recurring incidents and weakest on novel ones — the inverse of where value
is highest. LLM confidence is poorly calibrated, and "beats human baseline RCA accuracy" is not measurable as
stated.

## Decision
Frame Aegis as a **triage accelerator + known-pattern remediator**. **Auto-remediation requires a validated
precedent above a similarity threshold**; otherwise escalate to a human. **Prefer abstention over guessing**;
**calibrate confidence on historical outcomes**; require corroborating **live** evidence before accepting a
retrieved precedent. Measure RCA via **historical-replay eval in CI** (precision/recall + abstention rate).

## Alternatives considered
Confidence-threshold gating on raw LLM self-reported confidence (miscalibrated); autonomous action on novel
incidents (highest hallucination risk).

## Consequences
(+) Honest capability framing; autonomy only where it's safe; measurable quality. (−) Lower autonomous coverage
on novel incidents — accepted; those go to humans.
