# ADR-014 — PDP/PEP split, independent credential issuer, hash-chained audit

**Status:** Accepted · **Date:** 2026-06-19

## Context
The Action Executor concentrated dangerous privilege (it both decided and executed and minted credentials),
and the audit log was only "append-only" (mutable by a DBA).

## Decision
Split the Policy Decision Point (PDP) from the Policy Enforcement Point (PEP). An independent **credential
issuer** mints scoped, short-lived credentials only after verifying a **signed approval record** — it does not
trust the executor. Make the audit log **hash-chained** (each record commits the prior record's hash), anchored
periodically to WORM/object storage.

## Alternatives considered
Trusting the executor to self-attest approval (single point of compromise); plain append-only audit (not
tamper-evident).

## Consequences
(+) No single component can unilaterally cause or forge an authorized action; audit is tamper-evident for
compliance. (−) More moving parts on the action path and a signing/key-management requirement.
