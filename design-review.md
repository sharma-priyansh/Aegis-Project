# Aegis — Staff Engineer Design Review

**Reviewer role:** Staff Engineer (acting), adversarial design review
**Subject:** `architecture.md` v1.0, `requirements.md` v1.0
**Date:** 2026-06-19
**Verdict:** Strong, coherent design with a sound safety-first spine. It is, however, **overscoped for v1**,
**leans on a weak locking primitive for its most dangerous path**, and **oversells AI capability on exactly
the incidents that matter most (novel ones)**. Below: findings by category with severity, then the concrete
architecture changes I'm requiring, then ADRs.

Severity legend: **[S1]** must-fix before build · **[S2]** fix before autonomy in prod · **[S3]** improvement.

---

## 1. Weaknesses

**W1 [S1] — Incident ownership relies on a Redis TTL lock (Redlock-style) for a safety-critical path.**
Redis locks under failover are not a reliable mutual-exclusion primitive (the well-known Kleppmann
critique): a lock can be considered held by two owners across a primary failover, and a TTL expiry +
GC pause can let a "dead" owner wake up and act. For *advisory* coordination that's fine; for "who is
allowed to mutate production" it is not. The v1 design partly mitigates with a fencing token + Postgres
optimistic concurrency, but the **token originates from Redis**, which is the weak link. → See Improvement I1.

**W2 [S2] — Detection & Correlation is the hardest component and is hand-waved.** "Topology- and
time-aware correlation of N signals into one incident" is an unsolved-in-general streaming problem
(alert grouping / event correlation). The doc treats it as a single box with "statistical/ML detectors."
This is where most real AIOps products live or die, and it is underspecified. → I7.

**W3 [S2] — The "beats human baseline RCA accuracy" success metric is not measurable as written.** There
is rarely clean ground truth for "the root cause." Without a defined eval (historical replay + labeled
root-cause classes + abstention accounting), this metric invites self-deception. → I6.

**W4 [S3] — Latency budget is optimistic.** p95 < 30 s to first hypothesis while doing multi-query
expansion → hybrid retrieval → cross-encoder re-rank → multi-agent reasoning → possible escalation to a
large model is aggressive. The re-ranker and large-model hop are serial latency. Either the budget loosens
or the pipeline must short-circuit aggressively on known patterns. → I6.

**W5 [S3] — "Append-only Postgres audit log" is not tamper-evident.** A DBA or compromised service can
mutate rows. Compliance claims (SOC2-grade, "immutable") need cryptographic chaining or WORM storage. → I4.

---

## 2. Overengineering

**O1 [S2] — Event sourcing + CQRS + transactional outbox + saga + schema registry + service mesh +
multi-tenancy, all in v1.** This is a maximalist menu. Incidents are *not* a high-frequency financial
ledger; full event sourcing of incident state buys little over a checkpointed state machine plus an
append-only audit log, and it adds real projection/versioning complexity. **Keep** the transactional
outbox (cheap, prevents lost events) and saga (needed for safe rollback). **Defer** event-sourcing/CQRS,
service mesh, and multi-tenancy until scale/requirements demand them. → I2.

**O2 [S2] — Eleven microservices is too many for the actual cardinality of state.** Normalizer and
Detection share a pipeline and can be one service. Agent Workers as a separate service from the
Orchestrator fights LangGraph's in-process execution model and adds serialization/latency for little
benefit at v1 scale. Communicator (an agent) and Notification (a service) overlap. → I2 collapses this
to ~7 services.

**O3 [S3] — Three separate vector collections + hybrid + re-rank + parent-doc + multi-query from day one.**
Each adds latency/cost. Start with dense retrieval + metadata filter + one collection; add hybrid and
re-rank only where retrieval evals show they're needed. Premature retrieval optimization is still premature
optimization (per the project's own CLAUDE.md).

---

## 3. Scalability Concerns

**SC1 [S2] — Partition-key mismatch in the correlation stage.** You cannot partition by `incident_id`
*before the incident exists*. Pre-incident signals are keyed by `service`, but correlation is an inherently
**cross-key, stateful streaming join** (signals from service A and its dependency B must meet). This needs
either a dedicated stateful stream processor (Kafka Streams / Flink) with a keyed state store, or a
deterministic windowed grouper — not a naive consumer. The v1 doc's clean `incident_id` partitioning only
applies *after* correlation. → I7.

**SC2 [S2] — Hot partitions on the dependency hub.** A single high-fan-in service (the "everyone calls it"
monolith or the shared DB) dominates `signals.normalized[service]`, and a single large prod namespace
dominates `actions.*[namespace]`, serializing remediation exactly when a big blast-radius incident hits.
→ I7 (sub-keying / salting + per-tier concurrency).

**SC3 [S3] — Observability data volume is itself a scaling/cost problem.** Ingesting ≥100k signals/min and
retaining raw traces is a storage-and-egress firehose. Without retention tiering this dominates cost and
Postgres/audit write load. → I8.

---

## 4. Security Concerns

**SEC1 [S1] — The Action Executor concentrates dangerous privilege.** It mints JIT scoped credentials
*and* executes. If it's compromised or buggy, it is the single point that can do harm. Classic fix:
**split Policy Decision Point (PDP) from Policy Enforcement Point (PEP)**, and have an independent
**credential issuer** that re-verifies a *signed approval record* before minting a credential — it must
not trust the executor's word that "this was approved." → I3.

**SEC2 [S1] — The design implicitly trusts the LLM to resist prompt injection.** Telemetry, logs, and docs
are attacker-influenceable (anyone who can write a log line can attempt injection). LLMs do **not** reliably
maintain a data/instruction boundary. The design must **assume injection succeeds** and guarantee it still
cannot cause harm — which it nearly does via catalog + HITL, but only if *no* LLM output can ever directly
trigger an action and every action parameter is schema-validated against the catalog. Make this a stated
invariant, not an aspiration. → I3.

**SEC3 [S2] — Kill switch semantics are undefined for in-flight sagas.** Hitting the kill switch mid-saga
could leave infrastructure half-remediated. The kill switch must define: stop-and-hold vs. roll-back-then-stop,
and who is authorized to flip it. → I3.

**SEC4 [S3] — Multi-tenancy on shared Kafka/Qdrant via RLS is leak-prone** and is being added before it's
needed. Defer (O1); when added, prefer hard isolation (topic/collection per tenant + separate credentials)
over row-level filters.

---

## 5. Cost Concerns

**C1 [S2] — High always-on fixed cost.** Kafka + Postgres (primary+replicas) + Redis cluster + Qdrant
(sharded+replicated) + full OTel stack (Tempo/Prometheus/Loki) + service mesh is a heavy 24/7 footprint
**independent of incident volume**. For a system whose value is event-driven and bursty, the fixed cost
is disproportionate early. → I2 (cut service mesh/CQRS) + I8 (managed/optional backends, right-sizing).

**C2 [S2] — Per-incident LLM cost is unbounded in the worst case.** Multi-agent × multi-query × re-rank ×
escalation-to-large-model × diagnose/verify loops can stack tokens, and the most expensive incidents
(novel, looping) are the ones that escalate hardest. → I5 (hard per-incident budget + abstention + loop caps).

**C3 [S3] — Re-ranker and embedding model serving** are continuous GPU/CPU cost. Tie their use to measured
retrieval gain (O3).

---

## 6. Operational Concerns

**OP1 [S1] — Aegis must be more reliable than everything it watches, and must not become a dependency of
incident response.** If Aegis is degraded during a real outage, it cannot be allowed to *block* or *slow*
the humans. Required: Aegis fails **safe to deterministic paging**, runs in a **separate failure domain**
from the systems it remediates, and the human paging path never transits the AI tier. → I9.

**OP2 [S2] — Cold start: no corpus, no value.** RAG quality (and therefore the whole value prop) depends on
a curated runbook/postmortem corpus that doesn't exist on day one. The rollout must seed the corpus and run
**suggest-only** until retrieval evals clear a bar. → roadmap Phase 2–3 already staged; make it a gate, not a hope.

**OP3 [S2] — Action-catalog + rollback-definition maintenance is permanent toil** and a safety dependency:
a wrong rollback definition is worse than none. Needs catalog tests / dry-run simulation in CI and a review
gate on catalog changes. → I3.

**OP4 [S3] — Self-monitoring loop is a footgun.** Aegis watching Aegis can auto-remediate itself into a
cascading loop. v1 should **remove** self-remediation; Aegis is monitored by a separate, simpler system. → I9.

**OP5 [S3] — Automation complacency.** Operators will rubber-stamp confident-looking plans. Mitigate with
forced-justification UX, surfaced uncertainty/abstention, and tracked human-override rates. → I6.

---

## 7. AI Failure Modes

**AI1 [S1] — Inverse value curve: Aegis is best where it's least needed.** RAG/episodic memory excels on
**recurring** incidents (low value — often already automated by simple runbooks) and is weakest on **novel**
incidents (highest value, no precedent, model most likely to hallucinate). The honest framing: Aegis is a
**triage accelerator + known-pattern auto-remediator**, not a novel-incident oracle. Autonomy must be
**precedent-gated**: no auto-action without a sufficiently similar, validated past resolution. → I6.

**AI2 [S2] — LLM confidence is poorly calibrated**, yet the design gates planning on a confidence threshold.
Calibrate against historical outcomes, prefer **abstention** ("I don't know → escalate to human") over a
confident guess, and never treat self-reported confidence as probability. → I6.

**AI3 [S2] — Episodic-retrieval anchoring.** A plausible-but-wrong "similar past incident" can anchor the
Diagnostician and produce a confidently wrong RCA. Require corroborating *live* evidence before accepting a
retrieved precedent; treat retrieval as a hypothesis source, not an answer. → I6.

**AI4 [S3] — Eval is hard and will be skipped under pressure.** Bake historical-replay evaluation into CI
with labeled root-cause classes, tracking precision/recall *and* abstention rate. → I6.

---

## 8. Agent Failure Modes

**AG1 [S1] — Unbounded loops.** Diagnose → Plan → Execute → Verify(fail) → Diagnose can cycle indefinitely,
burning cost and possibly thrashing infrastructure. Require **hard iteration, wall-clock, and token/cost
budgets per incident**, with mandatory human escalation on exhaustion. → I5.

**AG2 [S2] — Context overflow on large incidents.** A storm produces thousands of signals; they cannot all
enter an agent context. Need deterministic pre-summarization/feature-extraction so the agent sees a faithful
digest, not a truncated arbitrary slice (truncation can drop the one signal that matters). → I7.

**AG3 [S2] — Checkpoint poisoning / resume-into-bad-state.** A corrupted or stale `IncidentState` checkpoint
could resume directly into an Execute node. Validate checkpoints on resume; never resume *into* an action
without re-checking approval + fencing token freshness. → I1/I3.

**AG4 [S3] — Stale-tool reasoning.** Read tools can return stale/cached infra state; the agent then reasons
on a false world. Stamp tool results with freshness and require re-read before acting on time-sensitive facts.

**AG5 [S3] — Partial-rollback inconsistency confuses the next diagnosis.** A saga that half-rolls-back leaves
a mixed state the Verifier/Diagnostician may misread. Make rollback state explicit in `IncidentState`.

---

## 9. Required Improvements (revised architecture deltas)

These are applied to `architecture.md` v1.1 (§17 revision log) and captured as ADRs.

- **I1 — Ownership without Redlock.** Single-driver comes from **Kafka single-consumer-per-partition** on
  `incidents.lifecycle[incident_id]` (the consumer group already guarantees one active owner per partition).
  The dangerous-path guard is a **monotonic fencing token sourced from a Postgres sequence** (linearizable),
  re-checked by the credential issuer and executor. Redis is demoted to advisory/perf only (dedup, cache),
  never correctness. *(Revises ADR-009.)*

- **I2 — Right-size v1.** Collapse to ~7 services (merge Normalizer→Detection; run agents in-process in the
  Orchestrator via LangGraph; fold Communicator into Notification). **Defer** event-sourcing/CQRS, service
  mesh, and multi-tenancy. **Keep** transactional outbox + saga. *(ADR-012 revised, ADR-013 new.)*

- **I3 — Harden the action path.** PDP/PEP split; an independent **credential issuer** mints scoped,
  short-lived creds only after verifying a **signed approval record**; every action parameter is
  schema-validated against the catalog; **no LLM output can directly trigger an action** (stated invariant);
  defined kill-switch semantics (stop-and-hold by default, roll-back-then-hold on request); catalog +
  rollback definitions tested/dry-run in CI. *(ADR-014, ADR-015 new.)*

- **I4 — Tamper-evident audit.** Append-only **hash-chained** audit (each record commits the prior record's
  hash); periodic anchoring to WORM/object storage. *(ADR-014.)*

- **I5 — Bound the agents.** Hard per-incident budgets (max diagnose↔verify iterations, wall-clock, tokens/$);
  circuit breakers on the LLM/router; mandatory human escalation on exhaustion. *(ADR-017 new.)*

- **I6 — Honest, precedent-gated AI.** Reframe Aegis as triage-accelerator + known-pattern remediator;
  **autonomy requires a validated precedent above a similarity threshold**; **abstention preferred over
  guessing**; confidence **calibrated** on historical outcomes; retrieved precedents require corroborating
  live evidence; **historical-replay eval in CI** (precision/recall + abstention). Replace the "beats human
  baseline" metric with replay-validated targets. *(ADR-016 new.)*

- **I7 — Specify correlation honestly.** Treat correlation as a **stateful streaming join** (Kafka Streams/
  Flink keyed state) and **start deterministic** (same/related service via topology edge + time window +
  signal-type rules); defer ML correlation until the deterministic baseline is measured. Salt/sub-key hot
  partitions; cap per-namespace remediation concurrency; deterministically **pre-summarize** signal storms
  before they reach agent context. *(ADR-018 new.)*

- **I8 — Cost discipline.** Signal/trace **retention tiering** (short hot TTL in Kafka, sampled cold to
  object storage); backends right-sized and swappable to managed offerings; re-ranker/hybrid gated on
  measured retrieval gain. *(ADR-020 new.)*

- **I9 — Aegis reliability isolation.** Aegis runs in a **separate failure domain** from its targets; the
  human paging path **never transits the AI tier**; degrade-safe to deterministic paging; **remove
  self-remediation** in v1 (Aegis is watched by a separate, simpler monitor). *(ADR-019 new.)*

---

## 10. What the design got right (keep)

Safety-first spine (deterministic detect→page works without AI); CP-on-the-action-path; governed action
catalog + HITL gate; externalized/checkpointed durable workflows; idempotency + saga rollback; OSS-first
model tiering; cloud-agnostic K8s-first; self-dogfooding OpenTelemetry. These are the load-bearing good
decisions and survive review unchanged.

---

## 11. Outcome

With I1–I9 applied, Aegis goes from "impressive but maximalist and slightly over-trusting of the AI" to
"defensible, right-sized, and safe under an explicit threat model where the LLM is assumed fallible and
even adversarial." The full decision set — original and revised — is recorded as ADRs in `docs/adr/`.
