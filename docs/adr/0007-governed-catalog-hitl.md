# ADR-007 — Governed action catalog + human-in-the-loop gate

**Status:** Accepted · **Date:** 2026-06-19

## Context
Agents must be able to remediate without ever performing unbounded or unauthorized actions.

## Decision
Agents may only request actions from a governed catalog (each with parameters, RBAC, risk tier, and a rollback
definition). Actions above a configured low-risk tier require human approval per policy.

## Alternatives considered
Open-ended agent tool use against infra (unbounded blast radius); fully manual (no automation value).

## Consequences
(+) Bounded blast radius, auditable, RBAC-enforced; out-of-catalog actions are structurally impossible.
(−) Catalog + rollback definitions are permanent maintenance toil and a safety dependency (see ADR-014, OP3).
